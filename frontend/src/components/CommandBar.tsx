import React, { useState, useRef, forwardRef, useImperativeHandle } from "react";

export interface CommandBarHandle {
  focus: () => void;
}

interface CommandBarProps {
  onSubmit: (cmd: string) => void;
}

const CommandBar = forwardRef<CommandBarHandle, CommandBarProps>(function CommandBar(
  { onSubmit },
  ref
) {
  const [cmd, setCmd] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));

  return (
    <div className="command-bar-container">
      <form
        onSubmit={(e: React.FormEvent<HTMLFormElement>) => {
          e.preventDefault();
          onSubmit(cmd);
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
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCmd(e.target.value)}
        />
        <button className="btn" type="submit">
          Go
        </button>
      </form>
    </div>
  );
});

export default CommandBar;
