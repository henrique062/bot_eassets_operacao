// Motivo: centralizar o modo de usuário local para desenvolvimento sem depender de registro no banco.
export const DEV_AUTH_ENABLED =
  import.meta.env.DEV && import.meta.env.VITE_DEV_TEST_USER === 'true';

// Motivo: token fixo para identificar sessão local de desenvolvimento e ajustar comportamento do frontend.
export const DEV_AUTH_TOKEN = 'dev-local-token';

const fallbackEmail = 'dev@local.test';
const normalizedEmail = (import.meta.env.VITE_DEV_TEST_EMAIL || fallbackEmail).trim().toLowerCase();

export function buildDevUser() {
  return {
    id: 0,
    email: normalizedEmail || fallbackEmail,
    role: 'dev',
  };
}
