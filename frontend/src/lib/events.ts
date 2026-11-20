import { useEffect } from "react";

// A tiny app-wide signal: "records changed, refresh what you show".
const EVENT = "smartspend:data-changed";

export function notifyDataChanged() {
  window.dispatchEvent(new Event(EVENT));
}

export function useOnDataChanged(handler: () => void) {
  useEffect(() => {
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
  }, [handler]);
}
