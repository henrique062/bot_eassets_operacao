import React from 'react';
import { FaCircleQuestion, FaTriangleExclamation, FaXmark } from 'react-icons/fa6';

export default function ConfirmModal({ title, message, onConfirm, onCancel, isAlert = false, confirmText = "Confirmar", cancelText = "Cancelar" }) {
    return (
        <div className="modal-overlay" onClick={isAlert ? onConfirm : onCancel} style={{ zIndex: 9999 }}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px', padding: '0', overflow: 'hidden' }}>
                <div className="modal-header" style={{ borderBottom: 'none', paddingBottom: '0' }}>
                    <h2 style={{ fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isAlert ? (
                            <>
                                <FaTriangleExclamation aria-hidden="true" />
                                Aviso
                            </>
                        ) : (
                            <>
                                <FaCircleQuestion aria-hidden="true" />
                                Confirmação
                            </>
                        )}
                    </h2>
                    <button className="modal-close" onClick={isAlert ? onConfirm : onCancel}>
                        <FaXmark aria-hidden="true" />
                    </button>
                </div>
                <div className="modal-body" style={{ padding: '24px', textAlign: 'center' }}>
                    <p style={{ marginBottom: '28px', fontSize: '1.05rem', color: 'var(--text-primary)', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                        {title && <strong style={{ display: 'block', marginBottom: '8px' }}>{title}</strong>}
                        {message}
                    </p>
                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
                        {!isAlert && (
                            <button 
                                onClick={onCancel} 
                                style={{ 
                                    flex: 1, 
                                    padding: '10px 0', 
                                    background: 'var(--bg-card)', 
                                    color: 'var(--text-primary)', 
                                    border: '1px solid var(--border-color)', 
                                    borderRadius: '8px', 
                                    cursor: 'pointer', 
                                    fontWeight: '500', 
                                    transition: 'all 0.2s' 
                                }}
                            >
                                {cancelText}
                            </button>
                        )}
                        <button 
                            onClick={onConfirm} 
                            style={{ 
                                flex: 1, 
                                padding: '10px 0', 
                                background: isAlert ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 77, 106, 0.15)', 
                                color: isAlert ? 'var(--accent-blue)' : 'var(--accent-red)', 
                                border: `1px solid ${isAlert ? 'rgba(59, 130, 246, 0.3)' : 'rgba(255, 77, 106, 0.3)'}`, 
                                borderRadius: '8px', 
                                cursor: 'pointer', 
                                fontWeight: '600',
                                transition: 'all 0.2s'
                            }}
                        >
                            {isAlert ? 'OK' : confirmText}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
