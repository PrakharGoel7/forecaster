type BrandMarkProps = {
  size?: number;
  className?: string;
};

export function BrandMark({ size = 28, className }: BrandMarkProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 128 128"
      role="img"
      aria-label="Angles logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="128" height="128" rx="28" fill="#193028" />
      <g fill="none" stroke="#d9f471" strokeWidth="10" strokeLinecap="round">
        <path d="M25 101 81 24" />
        <path d="M25 101 105 58" />
        <path d="M25 101 107 101" />
      </g>
      <circle cx="25" cy="101" r="9" fill="#f38164" />
    </svg>
  );
}
