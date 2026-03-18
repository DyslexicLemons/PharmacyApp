import type { RxState } from "@/types";

interface BadgeProps {
  state: RxState | string;
}

export default function Badge({ state }: BadgeProps) {
  return <span className={`badge state-${state}`}>{state}</span>;
}
