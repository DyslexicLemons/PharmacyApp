export default function Badge({ state }) {
  return <span className={`badge state-${state}`}>{state}</span>;
}