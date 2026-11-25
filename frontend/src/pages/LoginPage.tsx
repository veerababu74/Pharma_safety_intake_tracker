import { FormEvent, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import { Button, Card, Field, TextInput } from '../components/ui';

const SAMPLE = [
  { u: 'operator', p: 'Operator@123' },
  { u: 'operator2', p: 'Operator2@123' },
  { u: 'admin', p: 'Admin@123' },
  { u: 'admin2', p: 'Admin2@123' },
  { u: 'reviewer', p: 'Reviewer@123' },
  { u: 'reviewer2', p: 'Reviewer2@123' },
  { u: 'approver', p: 'Approver@123' },
  { u: 'approver2', p: 'Approver2@123' },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const toast = useToast();
  const [username, setUsername] = useState('operator');
  const [password, setPassword] = useState('Operator@123');
  const [loading, setLoading] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      toast.error('Login failed', err instanceof Error ? err.message : 'Check username and password');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-hero">
        <div className="brand-mark" style={{ width: 56, height: 56, fontSize: '1.35rem' }}>
          N
        </div>
        <h1>NovaCure Safety Intake</h1>
        <p>
          Fictional pharma intake, triage, hybrid RAG, and governed agent workflows — training prototype
          only.
        </p>
      </section>

      <section className="login-panel">
        <Card title="Log in">
          <p className="muted">Quick-fill sample users (2 accounts per role):</p>
          <div className="user-chip-row">
            {SAMPLE.map((s) => (
              <button
                key={s.u}
                type="button"
                className="user-chip"
                onClick={() => {
                  setUsername(s.u);
                  setPassword(s.p);
                }}
              >
                {s.u}
              </button>
            ))}
          </div>
          <form className="form-grid" onSubmit={onSubmit}>
            <Field label="Username">
              <TextInput value={username} onChange={(e) => setUsername(e.target.value)} required />
            </Field>
            <Field label="Password">
              <TextInput
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <Button type="submit" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </Card>
      </section>
    </div>
  );
}
