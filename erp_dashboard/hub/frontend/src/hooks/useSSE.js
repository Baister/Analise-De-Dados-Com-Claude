import { useEffect, useRef } from 'react';

// useSSE: abre EventSource em /stream?token=<...> e chama onBotUpdate(botKey)
// quando um bot finaliza ciclo. Reconecta automaticamente após 5s.
export function useSSE(onBotUpdate) {
  const cbRef = useRef(onBotUpdate);
  cbRef.current = onBotUpdate;

  useEffect(() => {
    if (!cbRef.current) return;
    const token = localStorage.getItem('erp_token');
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
  }, []); // cbRef mantém callback atualizado sem re-criar a conexão
}
