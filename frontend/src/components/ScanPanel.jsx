import { useRfidScan } from '../rfid';

/** Button + live "waiting for card" indicator tied to the ESP8266 reader. */
export default function ScanPanel({ mode = 'lookup', onScan, label = 'Scan ID card', hint }) {
  const { listening, error, start, stop } = useRfidScan(onScan, mode);
  return (
    <div className={`scan-panel ${listening ? 'live' : ''}`}>
      <div className="scan-ring" aria-hidden="true"><span /></div>
      <div className="scan-text">
        {listening ? (
          <>
            <strong>Waiting for a card</strong>
            <span>Hold the ID card on the reader. The display will confirm.</span>
          </>
        ) : (
          <>
            <strong>{label}</strong>
            <span>{error || hint || 'Press the button, then tap the card on the reader.'}</span>
          </>
        )}
      </div>
      {listening ? (
        <button className="btn ghost" type="button" onClick={stop}>Cancel</button>
      ) : (
        <button className="btn" type="button" onClick={start}>Start scan</button>
      )}
    </div>
  );
}
