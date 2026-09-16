import { useCallback, useEffect, useState } from 'react';

/**
 * Run an async function on mount and expose {data, error, loading, reload}.
 *
 * Results from a superseded call are discarded, so a slow first response
 * cannot overwrite a faster later one.
 */
export default function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [nonce, setNonce] = useState(0);

  // The caller owns the dependency list; this hook just threads it through.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);

  useEffect(() => {
    let live = true;
    setState((prev) => ({ ...prev, loading: true }));
    run()
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }));
    return () => {
      live = false;
    };
  }, [run, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, reload };
}
