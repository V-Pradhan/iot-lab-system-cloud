/** Round white badge with a microchip icon (Electronics Department mark). */
export default function Logo({ size = 44 }) {
  return (
    <span className="logo" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="6" y="6" width="12" height="12" rx="2" />
        <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
        <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
      </svg>
    </span>
  );
}
