import { useContext, useEffect, useRef, useState } from "react";
import { AuthContext } from "@/context/AuthContext";
import { lockPrescription, unlockPrescription, ApiError } from "@/api";

const HEARTBEAT_MS = 60_000; // refresh the 5-minute TTL every 60 s

/**
 * Acquires a view lock on a prescription while the component is mounted.
 *
 * - On mount: calls POST /prescriptions/{id}/lock.
 *   - 200 → lock owned; heartbeat starts.
 *   - 423 → another user holds it; `lockError` is set to their name.
 * - Every 60 s: re-calls the lock endpoint to refresh the Redis TTL.
 * - On unmount: sends DELETE /prescriptions/{id}/lock to release.
 *
 * Returns `{ lockError }`:
 *   - null  → we own the lock (or Redis is unavailable — fail open).
 *   - string → blocked; value is the "Prescription is currently open by X" message.
 */
export function usePrescriptionLock(prescriptionId: number | null | undefined) {
  const { token } = useContext(AuthContext);
  const [lockError, setLockError] = useState<string | null>(null);
  const [lockPending, setLockPending] = useState(true);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track whether we successfully acquired the lock so we only release if we own it.
  const ownedRef = useRef(false);

  useEffect(() => {
    if (!prescriptionId || !token) {
      setLockPending(false);
      return;
    }

    let cancelled = false;

    const acquire = () =>
      lockPrescription(prescriptionId, token)
        .then(() => {
          if (cancelled) return;
          ownedRef.current = true;
          setLockError(null);
          setLockPending(false);
          // Start heartbeat
          heartbeatRef.current = setInterval(() => {
            lockPrescription(prescriptionId, token).catch(() => {});
          }, HEARTBEAT_MS);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 423) {
            setLockError(err.message);
          }
          // Other errors (network, 404) — fail open, don't block the user
          setLockPending(false);
        });

    acquire();

    return () => {
      cancelled = true;
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      if (ownedRef.current && token) {
        ownedRef.current = false;
        unlockPrescription(prescriptionId, token).catch(() => {});
      }
    };
  }, [prescriptionId, token]);

  return { lockError, lockPending };
}
