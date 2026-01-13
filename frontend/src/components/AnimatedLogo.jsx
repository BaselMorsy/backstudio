import React, { useState, useEffect } from 'react';

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
 * AnimatedLogo Component (CSS Version)
 *
 * Cycles between {B/S} and Back Studio (or *B/S*, |B/S|, etc. depending on ACTIVE_CONTAINER)
 * Brackets are removed in expansion, and text is perfectly centered.
 */
const AnimatedLogo = () => {
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setIsExpanded((prev) => !prev);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  const gold = "#c8a951";
  const white = "#f5f1e8";

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '200px', backgroundColor: 'transparent' }}>
      <svg
        width="500"
        height="120"
        viewBox="0 0 500 120"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ overflow: 'visible' }}
      >
        <style>{`
          .transition-all { transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1); }
          .text-fade { transition: opacity 0.6s ease, transform 0.6s ease; }
          .serif-font { 
            font-family: "Didot", "Bodoni MT", "Playfair Display", serif; 
            font-weight: 600; 
            font-size: 60px; 
            letter-spacing: -0.5px;
          }
        `}</style>

        {/* Logo Group - centered at 250, 60 */}
        <g transform="translate(250, 60)">
          
          {/* LEFT CONTAINER - Hidden in expansion */}
          {ACTIVE_CONTAINER.left && (
            <path
              className="transition-all"
              d={ACTIVE_CONTAINER.left}
              stroke={gold}
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
              transform={`translate(${isExpanded ? -100 : 0}, 0)`}
              style={{ opacity: isExpanded ? 0 : 1 }}
            />
          )}

          {/* THE "B" SYMBOL (|>>) + "ack" */}
          <g className="transition-all" transform={`translate(${isExpanded ? -160 : -35}, 0)`}>
            {/* Vertical bar */}
            <line
              className="transition-all"
              x1="0" y1={isExpanded ? -30 : -20}
              x2="0" y2={isExpanded ? 30 : 20}
              stroke={gold}
              strokeWidth={isExpanded ? 7 : 6}
              strokeLinecap="round"
            />
            {/* >> part */}
            <path
              className="transition-all"
              d={isExpanded
                ? "M 16,-26 L 34,-15 L 16,-4 M 16,4 L 34,15 L 16,26"
                : "M 8,-16 L 18,-10 L 8,-4 M 8,4 L 18,10 L 8,16"
              }
              stroke={gold}
              strokeWidth={isExpanded ? 7 : 6}
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />

            <text
              x="48"
              y="22"
              fill={white}
              className="text-fade serif-font"
              style={{
                opacity: isExpanded ? 1 : 0,
                transform: `translateX(${isExpanded ? 0 : -5}px)`,
                transitionDelay: isExpanded ? '0.1s' : '0s'
              }}
            >
              ack
            </text>
          </g>

          {/* SLASH "/" */}
          <line
            x1="-5" y1="20" x2="5" y2="-20"
            stroke={gold}
            strokeWidth="5"
            strokeLinecap="round"
            className="transition-all"
            style={{
              opacity: isExpanded ? 0 : 1,
              transform: `scale(${isExpanded ? 0.8 : 1})`
            }}
          />

          {/* THE "S" SYMBOL (< >) + "tudio" */}
          <g className="transition-all" transform={`translate(${isExpanded ? -20 : 35}, 0)`}>
            {/* < part */}
            <path
              className="transition-all"
              d={isExpanded 
                ? "M 30,-26 L 8,-15 L 30,-4" 
                : "M -8,-16 L -18,-10 L -8,-4"
              }
              stroke={gold}
              strokeWidth={isExpanded ? 7 : 7}
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />
            {/* > part */}
            <path
              className="transition-all"
              d={isExpanded 
                ? "M 8,4 L 30,15 L 8,26" 
                : "M -18,4 L -8,10 L -18,16"
              }
              stroke={gold}
              strokeWidth={isExpanded ? 7 : 7}
              strokeLinecap="round"
              strokeLinejoin="miter"
              fill="none"
            />

            <text
              x="42"
              y="22"
              fill={white}
              className="text-fade serif-font"
              style={{ 
                opacity: isExpanded ? 1 : 0,
                transform: `translateX(${isExpanded ? 0 : -5}px)`,
                transitionDelay: isExpanded ? '0.2s' : '0s'
              }}
            >
              tudio
            </text>
          </g>

          {/* RIGHT CONTAINER - Hidden in expansion */}
          {ACTIVE_CONTAINER.right && (
            <path
              className="transition-all"
              d={ACTIVE_CONTAINER.right}
              stroke={gold}
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
              transform={`translate(${isExpanded ? 100 : 0}, 0)`}
              style={{ opacity: isExpanded ? 0 : 1 }}
            />
          )}

        </g>
      </svg>
    </div>
  );
};

export default AnimatedLogo;
