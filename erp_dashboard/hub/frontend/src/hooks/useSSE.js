import { useEffect, useRef } from 'react';

// useSSE: abre EventSource em /stream?token=<...> e chama onBotUpdate(botKey)
// quando um bot finaliza ciclo. Reconecta automaticamente após 5s.
// token: re-abre a conexão sempre que o token mudar (login/logout).
export function useSSE(onBotUpdate, token) {
  const cbRef = useRef(onBotUpdate);
  cbRef.current = onBotUpdate;

  useEffect(() => {
    if (!token) return;

    let es;
    let retryTimer;

    function connect() {
      es = new EventSource(`/stream?token=${token}`);
      es.addEventListener('update', (e) => {
        try {
          const { bot } = JSON.parse(e.data);
          cbRef.current?.(bot);
        } catch { /* ignorar parse errors */ }
      });
      es.onerror = () => {
        es.close();
        retryTimer = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => { es?.close(); clearTimeout(retryTimer); };
  }, [token]); // re-executa quando token muda (após login)
}
