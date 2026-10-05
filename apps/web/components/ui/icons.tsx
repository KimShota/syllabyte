import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 24, children, ...rest }: P) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const ChevronLeft = (p: P) => <Svg {...p}><path d="M15 5l-7 7 7 7" /></Svg>;
export const ChevronRight = (p: P) => <Svg {...p}><path d="M9 5l7 7-7 7" /></Svg>;
export const ChevronDown = (p: P) => <Svg {...p}><path d="M5 9l7 7 7-7" /></Svg>;
export const Close = (p: P) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>;
export const Check = (p: P) => <Svg {...p}><path d="M5 12.5l4.5 4.5L19 7.5" /></Svg>;
export const Play = (p: P) => <Svg {...p} fill="currentColor" stroke="none"><path d="M8 5.5v13a1 1 0 001.5.86l10.4-6.5a1 1 0 000-1.72L9.5 4.64A1 1 0 008 5.5z" /></Svg>;
export const Pause = (p: P) => <Svg {...p} fill="currentColor" stroke="none"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></Svg>;
export const More = (p: P) => <Svg {...p} fill="currentColor" stroke="none"><circle cx="12" cy="5" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="12" cy="19" r="1.8" /></Svg>;
export const Info = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></Svg>;
export const Replay = (p: P) => <Svg {...p}><path d="M4 12a8 8 0 108-8H7" /><path d="M7 1.5L4 4.5 7 7.5" /></Svg>;
export const ArrowUp = (p: P) => <Svg {...p}><path d="M12 19V5M6 11l6-6 6 6" /></Svg>;
export const ArrowDown = (p: P) => <Svg {...p}><path d="M12 5v14M6 13l6 6 6-6" /></Svg>;
export const ListIcon = (p: P) => <Svg {...p}><path d="M4 7h16M4 12h16M4 17h10" /></Svg>;
export const BarsIcon = (p: P) => <Svg {...p}><path d="M8 20V10M12 20V4M16 20v-7" /></Svg>;
export const DocIcon = (p: P) => <Svg {...p}><rect x="5" y="3" width="14" height="18" rx="3" /><path d="M9 9h6M9 13h6M9 17h3" /></Svg>;
export const Captions = (p: P) => <Svg {...p}><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M10 10.5a2 2 0 100 3M16 10.5a2 2 0 100 3" /></Svg>;
export const Notes = (p: P) => <Svg {...p}><path d="M5 4h10l4 4v12H5z" /><path d="M9 12h6M9 16h4" /></Svg>;
export const Transcript = (p: P) => <Svg {...p}><path d="M4 6h16M4 11h16M4 16h10" /></Svg>;
export const Edit = (p: P) => <Svg {...p}><path d="M4 20l4-1 11-11-3-3L5 16z" /></Svg>;
