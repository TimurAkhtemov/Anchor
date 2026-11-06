/** Numbered section rule: the Roman numeral carries the fixed reading order. */
export function SectionHead({ numeral, title }: { numeral: string; title: string }) {
  return (
    <div className="mb-3 flex items-baseline gap-3 border-t border-rule pt-3">
      <span className="font-data text-[11.5px] font-medium tracking-[0.14em] text-pencil">
        {numeral}
      </span>
      <h2 className="m-0 font-display text-[27px] leading-[1.15] font-normal tracking-[-0.012em]">
        {title}
      </h2>
    </div>
  );
}
