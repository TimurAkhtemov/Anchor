/** A bar growing from a centre rule: right and blue above zero, left and bronze
 *  below. `maxAbs` is the largest magnitude in the set, which fills half the width. */
export function DivergingBar({
  value,
  maxAbs,
}: {
  value: number | null;
  maxAbs: number;
}) {
  const width = value !== null && maxAbs > 0 ? (Math.abs(value) / maxAbs) * 50 : 0;
  const up = value !== null && value >= 0;
  return (
    <div className="relative h-3.5" aria-hidden="true">
      <span className="absolute -top-[3px] -bottom-[3px] left-1/2 w-px bg-ink-faint" />
      {width > 0 && (
        <span
          className={`absolute top-0.5 h-2.5 ${up ? "left-1/2 bg-ahead" : "right-1/2 bg-behind"}`}
          style={{ width: `${width}%` }}
        />
      )}
    </div>
  );
}
