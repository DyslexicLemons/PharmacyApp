import React from "react";

export default function BackButton({ onBack }) {
  if (!onBack) return null;

  return (
    <button onClick={onBack} className="btn btn-secondary back-button-fixed">
      ← Back
    </button>
  );
}
