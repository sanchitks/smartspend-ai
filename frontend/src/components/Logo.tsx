export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight text-ink ${className}`}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#0e6b58" />
        <path
          d="M9 20.5c1.6 1.6 3.9 2.5 6.6 2.5 3.6 0 6.4-1.8 6.4-4.6 0-2.6-2-3.6-5.6-4.3-2.6-.5-3.6-1-3.6-2.1 0-1.1 1.2-1.9 3-1.9 1.7 0 3 .6 4 1.6"
          fill="none"
          stroke="#fff"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      </svg>
      SmartSpend <span className="text-brand">AI</span>
    </span>
  );
}
