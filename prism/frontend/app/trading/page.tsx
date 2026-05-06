import { Suspense } from "react";
import BuilderClient from "./BuilderClient";

export default function TradingPage() {
  return (
    <Suspense>
      <BuilderClient buildPath="ai" />
    </Suspense>
  );
}
