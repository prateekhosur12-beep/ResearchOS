import React from "react";

/**
 * Inline SVG icon set (no icon dependency, no external requests).
 * All icons are 16px line icons on a 24 viewBox with currentColor strokes.
 */

type IconProps = React.SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconPlus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
export const IconSearch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
);
export const IconPlay = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4.5v15l12-7.5-12-7.5Z" />
  </Svg>
);
export const IconStop = (p: IconProps) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </Svg>
);
export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 13 4 4L19 7" />
  </Svg>
);
export const IconMinus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14" />
  </Svg>
);
export const IconX = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
export const IconAlert = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 9v4M12 17h.01" />
    <path d="M10.3 3.9 2.5 17.2A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" />
  </Svg>
);
export const IconClock = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Svg>
);
export const IconChevronRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);
export const IconChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);
export const IconRefresh = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 11a8 8 0 1 0-2.3 5.6" />
    <path d="M20 4.5V11h-6.2" />
  </Svg>
);
export const IconExternal = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 4h6v6M20 4l-8.5 8.5" />
    <path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </Svg>
);
export const IconDoc = (p: IconProps) => (
  <Svg {...p}>
    <path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9l-6-6Z" />
    <path d="M13 3v6h6" />
  </Svg>
);
export const IconBeaker = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 3h6M10 3v6.2L5.6 17A2 2 0 0 0 7.3 20h9.4a2 2 0 0 0 1.7-3L14 9.2V3" />
    <path d="M7.5 14h9" />
  </Svg>
);
export const IconBranch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="6.5" cy="5.5" r="2.5" />
    <circle cx="6.5" cy="18.5" r="2.5" />
    <circle cx="17.5" cy="9.5" r="2.5" />
    <path d="M6.5 8v8M17.5 12v1a3 3 0 0 1-3 3h-6" />
  </Svg>
);
export const IconQuote = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 7H5.5A1.5 1.5 0 0 0 4 8.5V12h5V7Zm0 5v3a2 2 0 0 1-2 2H6" />
    <path d="M19 7h-3.5A1.5 1.5 0 0 0 14 8.5V12h5V7Zm0 5v3a2 2 0 0 1-2 2h-1" />
  </Svg>
);
export const IconRadar = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4" />
    <path d="M12 12 18 6" />
  </Svg>
);
export const IconDownload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 4v10m0 0 4-4m-4 4-4-4" />
    <path d="M5 18h14" />
  </Svg>
);
export const IconServer = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="4" width="16" height="6" rx="1.6" />
    <rect x="4" y="14" width="16" height="6" rx="1.6" />
    <path d="M8 7h.01M8 17h.01" />
  </Svg>
);
export const IconList = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
  </Svg>
);
export const IconTrash = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" />
    <path d="M6 7l1 12.2A1.8 1.8 0 0 0 8.8 21h6.4a1.8 1.8 0 0 0 1.8-1.8L18 7" />
  </Svg>
);
export const IconSpinner = ({ size = 16, className = "", ...rest }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    className={`animate-spin ${className}`}
    aria-hidden="true"
    {...rest}
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" fill="none" />
    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" fill="none" />
  </svg>
);

export const IconLogo = ({ size = 22 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="1.5" y="1.5" width="21" height="21" rx="6" fill="#2563EB" />
    <path d="M6.5 15.5 10 12l2.5 2 5-5.5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="17.5" cy="8.5" r="1.6" fill="#fff" />
  </svg>
);
