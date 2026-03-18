interface BackButtonProps {
  onBack?: () => void;
}

export default function BackButton({ onBack }: BackButtonProps) {
  if (!onBack) return null;

  return (
    <button onClick={onBack} className="btn btn-secondary back-button-fixed">
      ← Back
    </button>
  );
}
