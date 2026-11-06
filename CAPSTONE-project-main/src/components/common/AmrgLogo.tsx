/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';

interface AmrgLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showSubtitle?: boolean;
}

export const AmrgLogo: React.FC<AmrgLogoProps> = ({
  className = '',
  size = 'md',
  showSubtitle = true,
}) => {
  const [imageError, setImageError] = useState(false);

  const heights = {
    sm: 'h-6 sm:h-7',
    md: 'h-8 sm:h-9',
    lg: 'h-10 sm:h-12',
    xl: 'h-14 sm:h-16',
  };

  return (
    <div className={`flex flex-col justify-center select-none ${className}`}>
      <div className="flex items-center gap-3">
        {!imageError ? (
          <img
            src="/amrg-global-logo.png"
            alt="AMRG GLOBAL"
            className={`${heights[size]} w-auto object-contain shrink-0 drop-shadow-2xs`}
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-black text-slate-900 tracking-tight font-serif text-xl">
              AMRG
            </span>
            <span className="font-extrabold text-[#05466C] tracking-widest uppercase text-xs">
              GLOBAL
            </span>
          </div>
        )}
      </div>

      {showSubtitle && (
        <span className="text-[9.5px] uppercase tracking-wider text-slate-500 font-semibold mt-1 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#0A7C3B] shrink-0 inline-block"></span>
          <span>Corporate, Tax & Advisory · UAE</span>
        </span>
      )}
    </div>
  );
};
