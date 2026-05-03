import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import box

from forecaster.config import ForecasterConfig
from forecaster.models import ForecastMemo
from forecaster.forecaster_system import ForecasterSystem
from forecaster.kalshi import KalshiClient, KalshiEvent, KalshiMarket
from pathlib import Path as _Path

console = Console()


def _tty_ask(prompt: str, default: str = "q") -> str:
    """Read input directly from /dev/tty so it works even when stdin is piped."""
    try:
        with open("/dev/tty", "r") as tty:
            console.print(f"[bold cyan]{prompt}[/bold cyan] ", end="")
            val = tty.readline().strip()
            return val if val else default
    except OSError:
        return default


def _prob_style(p: float) -> str:
    if p >= 0.7:
        return "bold green"
    if p >= 0.4:
        return "bold yellow"
    return "bold red"


def _print_memo(memo: ForecastMemo) -> None:
    console.print()

    pct = f"{memo.final_probability * 100:.1f}%"
    raw_pct = f"{memo.raw_probability * 100:.1f}%"
    spread_str = f"{memo.probability_spread[0]*100:.1f}% – {memo.probability_spread[1]*100:.1f}%"

    console.print(Panel(
        Text.assemble(
            ("P(YES) = ", "bold"),
            (pct, _prob_style(memo.final_probability)),
            f"   (raw {raw_pct}, Platt ×{memo.calibration.platt_coefficient:.3f})",
        ),
        title="Forecast",
        border_style="blue",
        expand=False,
    ))

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="bold dim", width=22)
    table.add_column("Content")
    table.add_row("Ensemble runs", str(memo.num_ensemble_runs))
    table.add_row("Agents per run", str(memo.num_agents))
    table.add_row("Run probabilities", ", ".join(f"{p*100:.1f}%" for p in memo.ensemble_run_probabilities))
    if memo.num_ensemble_runs > 1:
        table.add_row("Spread", spread_str)
    table.add_row("Foreknowledge", memo.parsed_question.foreknowledge_risk.value)
    table.add_row("Reference class", memo.parsed_question.outside_view_reference_class)
    console.print(table)

    for i, agent in enumerate(memo.agent_forecasts):
        console.print(Panel(
            f"[bold]P = {agent.probability*100:.1f}%[/bold]  (base rate: {agent.outside_view_base_rate*100:.1f}%)\n\n"
            f"[bold]Outside:[/bold] {agent.outside_view_reasoning}\n\n"
            f"[bold]Inside:[/bold] {agent.inside_view_reasoning}\n\n"
            f"[bold]For:[/bold] {'; '.join(agent.key_factors_for)}\n"
            f"[bold]Against:[/bold] {'; '.join(agent.key_factors_against)}\n\n"
            f"[bold]Uncertainty:[/bold] {agent.uncertainty_reasoning}\n"
            f"[bold]Confidence:[/bold] {agent.epistemic_confidence}",
            title=f"Agent {agent.agent_id + 1}",
            border_style="dim",
        ))

    rec = memo.supervisor_reconciliation
    console.print(Panel(
        f"[bold]Disagreement:[/bold] {rec.disagreement_level}\n"
        + (f"[bold]Crux:[/bold] {rec.crux_of_disagreement}\n" if rec.crux_of_disagreement else "")
        + (f"[bold]Searches:[/bold] {'; '.join(rec.targeted_searches_conducted)}\n\n" if rec.targeted_searches_conducted else "\n")
        + f"[bold]Reconciled P:[/bold] {rec.reconciled_probability*100:.1f}%\n\n"
        + rec.reconciliation_reasoning,
        title="Supervisor",
        border_style="cyan",
    ))

    if memo.open_questions:
        console.print("[bold]Open Questions:[/bold]")
        for q in memo.open_questions:
            console.print(f"  [yellow]?[/yellow] {q}")

    if memo.foreknowledge_flags:
        console.print("[bold yellow]Foreknowledge Flags:[/bold yellow]")
        for f in memo.foreknowledge_flags:
            console.print(f"  ⚠  {f}")

    console.print(f"\n[dim]Forecasted at: {memo.forecasted_at.isoformat()}[/dim]")


def _run(question, context, output, model, agents, runs):
    config = ForecasterConfig(model=model, num_ensemble_runs=runs)
    system = ForecasterSystem(config)

    console.print(Panel.fit("[bold]Oracle Agentic Forecaster[/bold]", border_style="blue"))
    console.print(f"\n[bold]Question:[/bold] {question}\n")
    console.print("[bold]Pipeline:[/bold]")

    def on_step(name: str, status: str) -> None:
        if status == "running":
            console.print(f"  [dim]→[/dim] {name}...", end="")
        else:
            console.print(" [green]✓[/green]")

    try:
        memo = system.forecast(question, context, on_step=on_step)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise

    _print_memo(memo)

    if output:
        system.save_memo(memo, Path(output))
        console.print(f"\n[green]Memo saved →[/green] {output}")


@click.group()
def cli() -> None:
    """Oracle Agentic Forecaster"""


@cli.command()
@click.argument("question")
@click.option("--context", "-x", default=None, help="Additional context or resolution criteria")
@click.option("--output", "-o", default=None, help="Save memo to JSON file")
@click.option("--model", default="anthropic/claude-sonnet-4-6", show_default=True)
@click.option("--agents", default=3, show_default=True, help="Number of independent agents per run")
@click.option("--runs", default=1, show_default=True, help="Number of ensemble runs (use 3-10 for tighter CIs)")
def forecast(question, context, output, model, agents, runs) -> None:
    """Forecast the probability that a question resolves YES."""
    _run(question, context, output, model, agents, runs)


@cli.command("forecast-file")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None)
@click.option("--model", default="anthropic/claude-sonnet-4-6", show_default=True)
def forecast_file(input_file, output, model) -> None:
    """Forecast from a JSON file with keys: question, context (optional), agents, runs."""
    data = json.loads(Path(input_file).read_text())
    out = output or input_file.replace(".json", "_forecast.json")
    _run(
        question=data["question"],
        context=data.get("context"),
        output=out,
        model=model,
        agents=data.get("agents", 3),
        runs=data.get("runs", 1),
    )


def _markets_table(markets: list[KalshiMarket], page: int, has_next: bool) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title=f"[bold]Kalshi Live Markets[/bold]  (page {page})",
        title_style="bold white",
        pad_edge=True,
    )
    table.add_column("#", style="bold dim", width=4, justify="right")
    table.add_column("Ticker", style="cyan", width=24)
    table.add_column("Question", width=52)
    table.add_column("Yes Price", justify="right", width=10)
    table.add_column("Volume", justify="right", width=10)
    table.add_column("Closes", justify="center", width=8)

    for i, m in enumerate(markets, 1):
        price = m.mid_price
        price_str = f"{price*100:.1f}¢"
        price_style = "green" if price >= 0.6 else ("yellow" if price >= 0.35 else "red")

        vol = m.volume
        if vol >= 1_000_000:
            vol_str = f"{vol/1_000_000:.1f}M"
        elif vol >= 1_000:
            vol_str = f"{vol/1_000:.0f}K"
        else:
            vol_str = str(int(vol))

        q = m.yes_sub_title or m.ticker
        if len(q) > 50:
            q = q[:47] + "..."

        table.add_row(
            str(i),
            m.ticker,
            q,
            Text(price_str, style=price_style),
            vol_str,
            m.close_date,
        )

    footer = "[dim]Enter a number to select"
    if has_next:
        footer += " · [bold]n[/bold] for next page"
    footer += " · [bold]q[/bold] to quit[/dim]"
    table.caption = footer
    return table


def _comparison_panel(memo: ForecastMemo, market: KalshiMarket) -> Panel:
    forecaster_p = memo.final_probability
    kalshi_p = market.mid_price
    edge = forecaster_p - kalshi_p

    edge_str = f"{edge:+.1%}"
    if abs(edge) < 0.03:
        edge_label = "roughly in line"
        edge_style = "dim"
    elif edge > 0:
        edge_label = "forecaster thinks market is [bold green]underpriced[/bold green]"
        edge_style = "green"
    else:
        edge_label = "forecaster thinks market is [bold red]overpriced[/bold red]"
        edge_style = "red"

    lines = (
        f"[bold]Forecaster P(YES):[/bold]  {forecaster_p*100:.1f}%\n"
        f"[bold]Kalshi market price:[/bold]  {kalshi_p*100:.1f}¢ (mid)\n"
        f"[bold]Edge:[/bold]  [{edge_style}]{edge_str}[/{edge_style}]  — {edge_label}\n\n"
        f"[dim]Ticker:[/dim] {market.ticker}   "
        f"[dim]Closes:[/dim] {market.close_date}"
    )
    return Panel(lines, title="Forecaster vs. Market", border_style="blue", expand=False)


@cli.command()
@click.option("--filter", "-f", "query", default=None, help="Filter markets by keyword")
@click.option("--limit", default=20, show_default=True, help="Markets per page")
@click.option("--output", "-o", default=None, help="Save memo to JSON file")
@click.option("--model", default="anthropic/claude-sonnet-4-6", show_default=True)
@click.option("--agents", default=3, show_default=True)
@click.option("--runs", default=1, show_default=True)
@click.option("--key-id", default=None, envvar="KALSHI_API_KEY", help="Kalshi key ID (or set KALSHI_API_KEY)")
@click.option("--private-key-file", default=None, envvar="KALSHI_PRIVATE_KEY_FILE",
              help="Path to your Kalshi RSA private key file (or set KALSHI_PRIVATE_KEY_FILE)")
def kalshi(query, limit, output, model, agents, runs, key_id, private_key_file) -> None:
    """Browse live Kalshi markets and forecast a selected one."""
    import os
    key_id = key_id or os.environ.get("KALSHI_API_KEY")
    private_key_file = private_key_file or os.environ.get("KALSHI_PRIVATE_KEY_FILE")

    if not key_id or not private_key_file:
        console.print(
            "[yellow]Kalshi requires RSA key authentication.[/yellow]\n\n"
            "You need two things:\n"
            "  1. [bold]Key ID[/bold]      — the UUID shown on kalshi.com → Settings → API\n"
            "  2. [bold]Private key[/bold] — the .pem / .txt file downloaded when you created the key\n\n"
            "Pass them via flags:\n"
            "  [bold]--key-id KEY_ID --private-key-file /path/to/key.txt[/bold]\n\n"
            "Or set env vars (recommended — add to ~/.zshrc):\n"
            "  [bold]export KALSHI_API_KEY=your-key-id[/bold]\n"
            "  [bold]export KALSHI_PRIVATE_KEY_FILE=/path/to/key.txt[/bold]"
        )
        sys.exit(1)

    try:
        client = KalshiClient.from_files(key_id=key_id, private_key_path=private_key_file)
    except Exception as e:
        console.print(f"[red]Failed to load Kalshi credentials:[/red] {e}")
        sys.exit(1)
    config = ForecasterConfig(model=model, num_ensemble_runs=runs)
    system = ForecasterSystem(config)

    # ── Step 1: Browse events ──────────────────────────────────────────────
    if query:
        console.print(f"[dim]Searching events for '{query}'...[/dim]")

    all_events: list[KalshiEvent] = []
    ev_cursor: str | None = None
    max_pages = 10 if query else 1
    for _ in range(max_pages):
        try:
            batch, ev_cursor = client.get_events(limit=100, cursor=ev_cursor)
        except Exception as e:
            console.print(f"[red]Failed to fetch events:[/red] {e}")
            sys.exit(1)
        all_events += batch
        if not ev_cursor:
            break

    display_events = [e for e in all_events if e.matches(query)] if query else all_events
    if not display_events:
        suffix = f" matching '{query}'" if query else ""
        console.print(f"[yellow]No events found{suffix}.[/yellow]")
        sys.exit(0)

    # Build events table
    ev_table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                     title="[bold]Kalshi Live Events[/bold]", pad_edge=True)
    ev_table.add_column("#", style="bold dim", width=4, justify="right")
    ev_table.add_column("Category", width=14)
    ev_table.add_column("Title", width=58)
    ev_table.add_column("Subtitle", width=22)
    for i, e in enumerate(display_events, 1):
        ev_table.add_row(str(i), e.category, e.title, e.sub_title)
    ev_table.caption = "[dim]Enter a number to select · [bold]q[/bold] to quit[/dim]"

    console.print()
    console.print(ev_table)
    console.print()

    selected_event: KalshiEvent | None = None
    while selected_event is None:
        choice = _tty_ask(f"Select event [1-{len(display_events)}] or q to quit:").lower()
        if choice == "q":
            console.print("[dim]Exiting.[/dim]")
            sys.exit(0)
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(display_events):
                selected_event = display_events[idx]
            else:
                console.print(f"[red]Enter a number between 1 and {len(display_events)}.[/red]")
        else:
            console.print("[red]Enter a number or 'q'.[/red]")

    # ── Step 2: Pick a market within the event ────────────────────────────
    try:
        event_markets, _ = client.get_markets(limit=50, event_ticker=selected_event.event_ticker)
    except Exception as e:
        console.print(f"[red]Failed to fetch markets for event:[/red] {e}")
        sys.exit(1)

    if not event_markets:
        console.print("[yellow]No open markets found for this event.[/yellow]")
        sys.exit(0)

    selected: KalshiMarket
    if len(event_markets) == 1:
        selected = event_markets[0]
    else:
        console.print()
        console.print(_markets_table(event_markets, 1, has_next=False))
        console.print()
        chosen: KalshiMarket | None = None
        while chosen is None:
            choice = _tty_ask(f"Select market [1-{len(event_markets)}] or q to quit:").lower()
            if choice == "q":
                console.print("[dim]Exiting.[/dim]")
                sys.exit(0)
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(event_markets):
                    chosen = event_markets[idx]
                else:
                    console.print(f"[red]Enter a number between 1 and {len(event_markets)}.[/red]")
            else:
                console.print("[red]Enter a number or 'q'.[/red]")
        selected = chosen

    # Show selected market details
    console.print()
    console.print(Panel(
        f"[bold]{selected.question}[/bold]\n\n"
        f"[dim]Ticker:[/dim] {selected.ticker}   "
        f"[dim]Price:[/dim] {selected.mid_price*100:.1f}¢   "
        f"[dim]Closes:[/dim] {selected.close_date}\n\n"
        + (selected.resolution_context[:500] if selected.resolution_context else "[dim]No resolution rules available.[/dim]"),
        title="Selected Market",
        border_style="cyan",
    ))
    console.print()

    if _tty_ask("Run forecaster on this market? [Y/n]:").lower() in ("n", "no"):
        console.print("[dim]Cancelled.[/dim]")
        sys.exit(0)

    console.print(f"\n[bold]Pipeline:[/bold]")

    def on_step(name: str, status: str) -> None:
        if status == "running":
            console.print(f"  [dim]→[/dim] {name}...", end="")
        else:
            console.print(" [green]✓[/green]")

    try:
        memo = system.forecast(
            question=selected.question,
            context=selected.resolution_context or None,
            on_step=on_step,
        )
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise

    _print_memo(memo)
    console.print(_comparison_panel(memo, selected))

    if output:
        system.save_memo(memo, Path(output))
        console.print(f"\n[green]Memo saved →[/green] {output}")


if __name__ == "__main__":
    cli()
