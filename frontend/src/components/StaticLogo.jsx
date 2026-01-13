import React from 'react';

/**
 * Container/Bracket Styles
 * Swap the active container by changing which one is assigned to ACTIVE_CONTAINER
 */
const CONTAINERS = {
  CURLY: {
    name: 'curly',
    left: "M -45,-25 Q -50,-25 -50,-20 L -50,-8 Q -50,-3 -54,0 Q -50,3 -50,8 L -50,20 Q -50,25 -45,25",
    right: "M 35,-25 Q 40,-25 40,-20 L 40,-8 Q 40,-3 44,0 Q 40,3 40,8 L 40,20 Q 40,25 35,25"
  },
  ASTERISK: {
    name: 'asterisk',
    left: "M -48,-8 L -48,8 M -54,-4 L -42,4 M -54,4 L -42,-4",
    right: "M 38,-8 L 38,8 M 32,-4 L 44,4 M 32,4 L 44,-4"
  },
  PIPE: {
    name: 'pipe',
    left: "M -48,-25 L -48,25",
    right: "M 38,-25 L 38,25"
  },
  ANGLE: {
    name: 'angle',
    left: "M -40,-25 L -52,0 L -40,25",
    right: "M 40,-25 L 52,0 L 40,25"
  },
  SQUARE: {
    name: 'square',
    left: "M -45,-25 L -52,-25 L -52,25 L -45,25",
    right: "M 35,-25 L 42,-25 L 42,25 L 35,25"
  },
  ROUND: {
    name: 'round',
    left: "M -45,-25 Q -52,-25 -52,-20 L -52,20 Q -52,25 -45,25",
    right: "M 35,-25 Q 42,-25 42,-20 L 42,20 Q 42,25 35,25"
  },
  NONE: {
    name: 'none',
    left: "",
    right: ""
  }
};

// Change this to swap container styles: CURLY, ASTERISK, PIPE, ANGLE, SQUARE, ROUND, or NONE
const ACTIVE_CONTAINER = CONTAINERS.CURLY;

/**
 * StaticLogo Component
 *
 * Displays the contracted version of the logo ({B/S})
 * Can be used in navigation bars, headers, etc.
 */
const StaticLogo = ({ className = '', onClick = null, size = 'medium' }) => {
  const gold = "#c8a951";

  // Size configurations
  const sizes = {
    small: { width: 50, height: 35, scale: 0.5 },
    medium: { width: 70, height: 50, scale: 0.7 },
    large: { width: 90, height: 65, scale: 0.9 }
  };

  const sizeConfig = sizes[size] || sizes.medium;

  return (
    <div
      className={`inline-flex items-center justify-center ${onClick ? 'cursor-pointer' : ''} ${className}`}
      onClick={onClick}
    >
      <svg
        width={sizeConfig.width}
        height={sizeConfig.height}
        viewBox="-60 -35 120 70"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ overflow: 'visible' }}
      >
        {/* Logo Group - centered at origin */}
        <g transform={`scale(${sizeConfig.scale})`}>

          {/* LEFT CONTAINER */}
          {ACTIVE_CONTAINER.left && (
            <path
              d={ACTIVE_CONTAINER.left}
              stroke={gold}
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
            />
          )}

          {/* THE "B" SYMBOL (|>>) */}
          <g transform="translate(-35, 0)">
            {/* Vertical bar */}
            <line
              x1="0" y1="-20"
              x2="0" y2="20"
              stroke={gold}
              strokeWidth="6"
              strokeLinecap="round"
            />
            {/* >> part */}
            <path
              d="M 8,-16 L 18,-10 L 8,-4 M 8,4 L 18,10 L 8,16"
              stroke={gold}
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />
          </g>

          {/* SLASH "/" */}
          <line
            x1="-5" y1="20" x2="5" y2="-20"
            stroke={gold}
            strokeWidth="5"
            strokeLinecap="round"
          />

          {/* THE "S" SYMBOL (< >) */}
          <g transform="translate(35, 0)">
            {/* < part */}
            <path
              d="M -8,-16 L -18,-10 L -8,-4"
              stroke={gold}
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />
            {/* > part */}
            <path
              d="M -18,4 L -8,10 L -18,16"
              stroke={gold}
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />
          </g>

          {/* RIGHT CONTAINER */}
          {ACTIVE_CONTAINER.right && (
            <path
              d={ACTIVE_CONTAINER.right}
              stroke={gold}
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
            />
          )}

        </g>
      </svg>
    </div>
  );
};

export default StaticLogo;
