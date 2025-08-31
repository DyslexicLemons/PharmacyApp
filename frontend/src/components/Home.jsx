import React, { useEffect, useState } from "react";

import CommandBar from "@/Components/CommandBar";

export default function Home({ onCommand }) {
  return (
    <div className="vstack">
      <h1>🏥 Pharmacy Console</h1>
      <p>Type a command to navigate queues or open a patient profile.</p>
      <ul>
        <li>
          <code>Home</code> – Go back Home
        </li>
        <li>
          <code>qt</code> – Queue Triage
        </li>
        <li>
          <code>qv1</code> – Verify 1
        </li>
        <li>
          <code>qp</code> – Prep/Fill
        </li>
        <li>
          <code>qv2</code> – Final Verify
        </li>
        <li>
          <code>all</code> – All active prescriptions
        </li>
        <li>
          <code>drugs</code> – All drugs
        </li>
        <li>
          <code>patients</code> – All patients
        </li>
        <li>
          <code>lastname,firstname</code> – Open patient profile (e.g.,{" "}
          <code>smith,john</code>)
        </li>
      </ul>
      <CommandBar onSubmit={onCommand} />
    </div>
  );
}