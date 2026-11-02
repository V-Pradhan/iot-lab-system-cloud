import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';

/**
 * Wait for the next card scanned on the ESP8266 reader.
 * mode "register": the backend treats the next unknown card as a UID to capture.
 * mode "lookup"  : the backend tells the reader whether the card belongs to a student.
 * The browser polls /api/rfid/latest once a second until a scan arrives (max 60 s).
 */
export function useRfidScan(onScan, mode = 'lookup') {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const base = useRef(0);
  const timer = useRef(null);
  const limit = useRef(null);
  const cb = useRef(onScan);
  cb.current = onScan;

  const clear = () => { clearInterval(timer.current); clearTimeout(limit.current); };

  const stop = useCallback(async () => {
    clear();
    setListening(false);
    try { await api.del('/rfid/arm'); } catch { /* ignore */ }
  }, []);

  const start = useCallback(async () => {
    setError('');
    clear();
    try {
      const r = await api.post('/rfid/arm', { mode });
      base.current = r.baseline_id;
      setListening(true);
    } catch (e) {
      setError(e.message);
      return;
    }
    timer.current = setInterval(async () => {
      try {
        const d = await api.get(`/rfid/latest?after_id=${base.current}`);
        if (d.scan) {
          base.current = d.scan.id;
          clear();
          setListening(false);
          cb.current(d.scan);
        }
      } catch { /* keep polling */ }
    }, 1000);
    limit.current = setTimeout(() => { stop(); setError('No card scanned. Try again.'); }, 60000);
  }, [mode, stop]);

  useEffect(() => clear, []);
  return { listening, error, start, stop };
}
