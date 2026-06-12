import { useState } from 'react';
import { LuEye, LuEyeOff } from 'react-icons/lu';
import { buildDevUser, DEV_AUTH_ENABLED, DEV_AUTH_TOKEN } from '../config/devAuth';

const REMEMBER_KEY = 'auth.rememberEmail';

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState(() => localStorage.getItem(REMEMBER_KEY) || '');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(!!localStorage.getItem(REMEMBER_KEY));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Motivo: permitir acesso rápido para validação de UI/fluxos em ambiente local sem autenticação no banco.
  const handleDevLogin = () => {
    setError('');
    onLogin(DEV_AUTH_TOKEN, buildDevUser());
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const API_BASE = import.meta.env.VITE_API_BASE || '/api';
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data?.detail || 'Erro ao fazer login');
        return;
      }

      if (remember) {
        localStorage.setItem(REMEMBER_KEY, email.trim().toLowerCase());
      } else {
        localStorage.removeItem(REMEMBER_KEY);
      }

      onLogin(data.token, data.user);
    } catch {
      setError('Não foi possível conectar ao servidor');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        <div style={styles.logo}>
          <img src="/logo-full.svg" alt="Crypto Funding Rates" style={styles.logoImage} />
          <p style={styles.logoSub}>Acesse sua conta para continuar</p>
        </div>

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>E-mail</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="seu@email.com"
              required
              autoFocus
              style={styles.input}
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Senha</label>
            <div style={styles.passwordWrapper}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={{ ...styles.input, paddingRight: '44px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                style={styles.eyeBtn}
                tabIndex={-1}
                aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
              >
                {showPassword ? <LuEyeOff size={16} /> : <LuEye size={16} />}
              </button>
            </div>
          </div>

          <label style={styles.rememberRow}>
            <input
              type="checkbox"
              checked={remember}
              onChange={e => setRemember(e.target.checked)}
              style={styles.checkbox}
            />
            <span style={styles.rememberLabel}>Lembrar e-mail</span>
          </label>

          {error && <p style={styles.error}>{error}</p>}

          <button type="submit" disabled={loading} style={styles.submitBtn}>
            {loading ? 'Entrando...' : 'Entrar'}
          </button>

          {DEV_AUTH_ENABLED && (
            <button type="button" onClick={handleDevLogin} style={styles.devSubmitBtn}>
              Entrar com usuário de teste
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--bg-primary)',
    backgroundImage:
      'linear-gradient(140deg, rgba(6, 10, 22, 0.76) 0%, rgba(7, 11, 22, 0.88) 40%, rgba(8, 12, 24, 0.94) 100%), url("/login-background-4k.webp")',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
    backgroundSize: 'cover',
    padding: '24px',
  },
  card: {
    background: 'rgba(26, 31, 46, 0.86)',
    border: '1px solid rgba(95, 167, 255, 0.25)',
    borderRadius: 'var(--radius-xl)',
    padding: '40px',
    width: '100%',
    maxWidth: '400px',
    boxShadow: 'var(--shadow-modal)',
    backdropFilter: 'blur(6px)',
  },
  logo: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: '10px',
    marginBottom: '36px',
  },
  logoImage: {
    width: '270px',
    maxWidth: '100%',
    height: 'auto',
  },
  logoSub: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  label: {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text-secondary)',
  },
  input: {
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border-active)',
    borderRadius: 'var(--radius-sm)',
    padding: '12px 14px',
    color: 'var(--text-primary)',
    fontSize: '14px',
    width: '100%',
    outline: 'none',
    transition: 'border-color var(--transition)',
  },
  passwordWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  eyeBtn: {
    position: 'absolute',
    right: '12px',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--text-secondary)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '4px',
  },
  rememberRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    cursor: 'pointer',
    marginTop: '-4px',
  },
  checkbox: {
    width: '16px',
    height: '16px',
    accentColor: 'var(--accent-blue)',
    cursor: 'pointer',
  },
  rememberLabel: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
  },
  error: {
    fontSize: '13px',
    color: 'var(--accent-red)',
    background: 'var(--accent-red-bg)',
    borderRadius: 'var(--radius-sm)',
    padding: '10px 14px',
  },
  submitBtn: {
    background: 'var(--accent-blue)',
    color: '#fff',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    padding: '13px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'opacity var(--transition)',
    marginTop: '4px',
  },
  devSubmitBtn: {
    background: 'rgba(95, 167, 255, 0.14)',
    color: 'var(--text-primary)',
    border: '1px dashed rgba(95, 167, 255, 0.45)',
    borderRadius: 'var(--radius-sm)',
    padding: '11px 13px',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
  },
};
