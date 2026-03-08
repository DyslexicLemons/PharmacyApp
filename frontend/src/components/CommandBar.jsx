import { useState, useRef, forwardRef, useImperativeHandle } from "react";

const CommandBar = forwardRef(function CommandBar({ onSubmit }, ref) {
  const [cmd, setCmd] = useState("");
  const inputRef = useRef(null);

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));

  return (
    <div className="command-bar-container">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(cmd.trim());
          setCmd("");
          inputRef.current?.focus();
        }}
        className="hstack"
      >
        <input
          ref={inputRef}
          autoFocus
          className="input"
          placeholder="Type command:"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
        />
        <button className="btn" type="submit">
          Go
        </button>
      </form>
    </div>
  );
});

export default CommandBar;