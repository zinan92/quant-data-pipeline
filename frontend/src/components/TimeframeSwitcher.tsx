import { Timeframe } from "../types/timeframe";

interface Props {
  value: Timeframe;
  options: Timeframe[];
  onChange: (timeframe: Timeframe) => void;
}

const LABELS: Record<Timeframe, string> = {
  day: "日线",
  "30m": "30分钟"
};

export function TimeframeSwitcher({ value, options, onChange }: Props) {
  return (
    <div className="timeframe-switcher">
      {options.map((option) => (
        <button
          key={option}
          className={`timeframe-switcher__btn ${
            option === value ? "timeframe-switcher__btn--active" : ""
          }`}
          onClick={() => onChange(option)}
        >
          {LABELS[option]}
        </button>
      ))}
    </div>
  );
}
