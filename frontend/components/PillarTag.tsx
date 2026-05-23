import { PILLAR_LABEL, type Pillar } from "@/lib/types";

export function PillarTag({ pillar }: { pillar: Pillar }) {
  return (
    <span className={`pillar-tag pillar-${pillar}`} title={PILLAR_LABEL[pillar]}>
      <span className="pillar-tag__num">P{pillar}</span>
      <span className="pillar-tag__label">{PILLAR_LABEL[pillar]}</span>
    </span>
  );
}
