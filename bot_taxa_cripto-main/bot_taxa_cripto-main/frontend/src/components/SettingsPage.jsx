import { useState, useEffect } from 'react';
import { LuActivity } from 'react-icons/lu';
import { fetchUserSettings, updateUserSetting } from '../services/api';

export default function SettingsPage({ user, onNavigate }) {
    const [settings, setSettings] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            setLoading(true);
            const userRes = await fetchUserSettings();
            setSettings(userRes.settings || {});
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleSettingChange = (category, key, value) => {
        setSettings(prev => {
            const isApiKey = category.startsWith('api_keys_');
            const parsedValue = isApiKey ? value : (parseFloat(value) || 0);
            return {
                ...prev,
                [category]: {
                    ...prev[category],
                    value: {
                        ...(prev[category]?.value || {}),
                        [key]: parsedValue
                    }
                }
            };
        });
    };

    const handleSave = async (settingKey) => {
        try {
            setSaving(true);
            setError('');
            setSuccessMsg('');
            await updateUserSetting(settingKey, settings[settingKey]?.value);
            setSuccessMsg('Configurações salvas com sucesso!');
            setTimeout(() => setSuccessMsg(''), 3000);
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div style={{ padding: '24px' }}>Carregando configurações...</div>;

    return (
        <div style={{ maxWidth: '800px', padding: '24px 32px' }}>
            <h1 style={{ marginBottom: '24px', fontSize: '1.8rem' }}>Configurações do Sistema</h1>

            {error && <div className="error-message" style={{ marginBottom: '16px' }}>{error}</div>}
            {successMsg && <div style={{ background: 'rgba(0, 230, 138, 0.1)', color: 'var(--accent-green)', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontWeight: '500' }}>{successMsg}</div>}

            <div className="stat-card" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ marginBottom: '8px', color: 'var(--accent-green)' }}>Chaves de API (Conta Real)</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '20px' }}>
                    Configure suas credenciais da API para realizar operações em conta real. As chaves são armazenadas com segurança.
                </p>

                {/* Binance API Keys */}
                <div style={{ marginBottom: '20px' }}>
                    <h4 style={{ marginBottom: '12px', color: 'var(--text-primary)' }}>Binance Futures</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 'bold' }}>API Key</label>
                            <input
                                type="password"
                                placeholder="Insira a API Key da Binance"
                                value={settings.api_keys_binance?.value?.apiKey || ''}
                                onChange={(e) => handleSettingChange('api_keys_binance', 'apiKey', e.target.value)}
                                style={{ width: '100%', padding: '10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 'bold' }}>API Secret</label>
                            <input
                                type="password"
                                placeholder="Insira o API Secret da Binance"
                                value={settings.api_keys_binance?.value?.apiSecret || ''}
                                onChange={(e) => handleSettingChange('api_keys_binance', 'apiSecret', e.target.value)}
                                style={{ width: '100%', padding: '10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                            />
                        </div>
                    </div>
                    <div style={{ marginTop: '16px', textAlign: 'right' }}>
                        <button 
                            className="btn-primary" 
                            onClick={() => handleSave('api_keys_binance')}
                            disabled={saving}
                            style={{ padding: '8px 16px', borderRadius: '6px', fontWeight: 'bold', fontSize: '0.9rem' }}
                        >
                            {saving ? 'Salvando...' : 'Salvar Binance'}
                        </button>
                    </div>
                </div>

                <hr style={{ borderTop: '1px solid var(--border-color)', margin: '20px 0' }} />

                {/* Bybit API Keys */}
                <div>
                    <h4 style={{ marginBottom: '12px', color: 'var(--text-primary)' }}>Bybit Futures</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                        <div>
                            <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 'bold' }}>API Key</label>
                            <input
                                type="password"
                                placeholder="Insira a API Key da Bybit"
                                value={settings.api_keys_bybit?.value?.apiKey || ''}
                                onChange={(e) => handleSettingChange('api_keys_bybit', 'apiKey', e.target.value)}
                                style={{ width: '100%', padding: '10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 'bold' }}>API Secret</label>
                            <input
                                type="password"
                                placeholder="Insira o API Secret da Bybit"
                                value={settings.api_keys_bybit?.value?.apiSecret || ''}
                                onChange={(e) => handleSettingChange('api_keys_bybit', 'apiSecret', e.target.value)}
                                style={{ width: '100%', padding: '10px', background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', color: 'white', borderRadius: '6px' }}
                            />
                        </div>
                    </div>
                    <div style={{ marginTop: '16px', textAlign: 'right' }}>
                        <button 
                            className="btn-primary" 
                            onClick={() => handleSave('api_keys_bybit')}
                            disabled={saving}
                            style={{ padding: '8px 16px', borderRadius: '6px', fontWeight: 'bold', fontSize: '0.9rem' }}
                        >
                            {saving ? 'Salvando...' : 'Salvar Bybit'}
                        </button>
                    </div>
                </div>
            </div>

            {user?.role === 'admin' && (
                <div className="stat-card" style={{ padding: '24px', marginBottom: '24px', borderColor: 'var(--accent-blue)' }}>
                    <h3 style={{ marginBottom: '8px', color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <LuActivity /> Diagnóstico de Score (Admin)
                    </h3>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '20px' }}>
                        Visualize em tempo real como cada componente do algoritmo (APY Líquido, Volume, Intervalo, Consistência Histórica) contribui para o score de cada ativo. Útil para entender e validar o comportamento do algoritmo.
                    </p>
                    <button
                        onClick={() => onNavigate('score-diagnostics')}
                        className="btn-primary"
                        style={{ padding: '10px 24px', borderRadius: '8px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <LuActivity size={16} />
                        Abrir Diagnóstico de Score
                    </button>
                </div>
            )}

        </div>
    );
}
