import {  useState } from "react";


export default function CommandBar({ onSubmit }) {
  const [cmd, setCmd] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(cmd.trim());
        setCmd("");
      }}
      className="hstack"
    >
      <input
        className="input"
        placeholder="Type command:"
        value={cmd}
        onChange={(e) => setCmd(e.target.value)}
      />
      <button className="btn" type="submit">
        Go
      </button>
    </form>
  );
}