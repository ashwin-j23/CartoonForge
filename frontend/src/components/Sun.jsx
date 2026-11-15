export default function Sun({ size = 40, className = '' }) {
  return (
    <svg className={`sun ${className}`} viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">
      <g className="sun-rays" stroke="#FFB020" strokeWidth="5" strokeLinecap="round">
        <path d="M32 3v8M32 53v8M3 32h8M53 32h8M11.5 11.5l5.7 5.7M46.8 46.8l5.7 5.7M11.5 52.5l5.7-5.7M46.8 17.2l5.7-5.7" />
      </g>
      <circle cx="32" cy="32" r="17" fill="#FFC93C" stroke="#FFB020" strokeWidth="2" />
      <circle cx="25.5" cy="29" r="2.6" fill="#2D2846" />
      <circle cx="38.5" cy="29" r="2.6" fill="#2D2846" />
      <circle cx="21.5" cy="35" r="2.6" fill="#FF7B6B" opacity=".7" />
      <circle cx="42.5" cy="35" r="2.6" fill="#FF7B6B" opacity=".7" />
      <path d="M24.5 36.5c2 4 5 5.5 7.5 5.5s5.5-1.5 7.5-5.5" fill="none" stroke="#2D2846" strokeWidth="2.8" strokeLinecap="round" />
    </svg>
  )
}
