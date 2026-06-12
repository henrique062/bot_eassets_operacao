import { useState } from 'react';
import {
    FaBook,
    FaBrain,
    FaBullseye,
    FaChartLine,
    FaCircle,
    FaCircleCheck,
    FaLightbulb,
    FaMapPin,
    FaSeedling,
    FaTriangleExclamation,
    FaScaleBalanced,
    FaMagnifyingGlassChart,
    FaGears,
    FaShieldHalved
} from 'react-icons/fa6';

const STRATEGIES = [
    {
        id: 'direcional',
        icon: <FaSeedling aria-hidden="true" />,
        name: 'Pegar a Taxa (Favor do Funding)',
        risk: 'Alto',
        riskColor: '#ff4d6a',
        description: 'Você recebe o funding rate mas fica exposto na direção oposta à maioria.',
        how: [
            'Funding positivo (maioria em Long) → Abra SHORT para receber a taxa',
            'Funding negativo (maioria em Short) → Abra LONG para receber a taxa',
            'Esta estratégia busca lucro passivo contínuo através da taxa ganha'
        ],
        pros: ['Recebe lucros previsíveis a cada ciclo de pagamento (8h/4h)', 'Potencializa lucros em mercados estagnados ou que corrigem contra a tendência'],
        cons: ['Risco direcional alto se o mercado não reverter e continuar contra sua posição'],
        tip: 'Avalie a volatilidade: o lucro da taxa precisa compensar os riscos de variação cambial da moeda (Price PnL negativo).',
    },
    {
        id: 'counter',
        icon: <FaBrain aria-hidden="true" />,
        name: 'Estratégia de Contra-Tendência',
        risk: 'Médio',
        riskColor: '#fbbf24',
        description: 'Você PAGA a taxa de funding, mas opera a favor da tendência para lucrar na variação de preço.',
        how: [
            'Funding positivo → Abra LONG (Você paga a taxa, aposta que continuará subindo)',
            'Funding negativo → Abra SHORT (Você paga a taxa, aposta que continuará caindo)',
            'Pode antecipar ou seguir as fortes tendências do mercado (Rompimentos/Squeezes)'
        ],
        pros: ['Lucro com fortes tendências e explosões (squeezes) a favor do movimento', 'Ignora limites de range, capturando o Price PnL massivo'],
        cons: ['Custo de manutenção mais alto (você paga a taxa a cada ciclo)', 'Diminui os lucros totais se a moeda demorar a andar'],
        tip: 'Ótima para ativos com muita tração; o ideal é que a variação de preço pague as taxas de manutenção e deixe lucros expressivos.',
    },
    {
        id: 'management',
        icon: <FaChartLine aria-hidden="true" />,
        name: 'Gestão de Funding vs Preço',
        risk: 'Médio',
        riskColor: '#fbbf24',
        description: 'Como analisar o resultado global (Total PnL) da sua operação.',
        how: [
            'Funding PnL: Dinheiro recebido (ou pago) por manter a posição aberta',
            'Price PnL: Dinheiro ganho ou perdido com a subida/descida do ativo em si',
            'Total PnL: A soma do Funding PnL + Price PnL, deduzindo as taxas de negociação da Exchange',
            'Sempre proteja seu capital baseando-se no Total PnL'
        ],
        pros: ['Clareza total sobre a fonte do lucro na sua carteira', 'Impede a ilusão de "ganhar no funding, mas devolver tudo na desvalorização do ativo"'],
        cons: ['Exige disciplina manual e acompanhamento pelo App ou na corretora', 'Envolve saber estopar operações, mesmo recebendo taxas'],
        tip: 'Vigie as colunas de PnL na sua "Tabela de Histórico de Trades". O saldo total é o que importa no final do dia.',
    }
];

export default function StrategyPanel() {
    const [activeTab, setActiveTab] = useState('qualificacao');
    const [expanded, setExpanded] = useState(null);

    return (
        <div className="strategy-panel">
            <div className="strategy-header">
                <h2 className="icon-inline">
                    <FaBook aria-hidden="true" />
                    Base de Conhecimento Vorxia
                </h2>
                <p className="strategy-subtitle">
                    Entenda como a IA seleciona moedas e as melhores estratégias operacionais.
                </p>
            </div>

            <div className="strategy-tabs-nav">
                <button
                    className={`tab-btn ${activeTab === 'qualificacao' ? 'active' : ''}`}
                    onClick={() => setActiveTab('qualificacao')}
                >
                    <FaScaleBalanced /> Qualificação de Moedas
                </button>
                <button
                    className={`tab-btn ${activeTab === 'estrategias' ? 'active' : ''}`}
                    onClick={() => setActiveTab('estrategias')}
                >
                    <FaBullseye /> Estratégias
                </button>
                <button
                    className={`tab-btn ${activeTab === 'tabela' ? 'active' : ''}`}
                    onClick={() => setActiveTab('tabela')}
                >
                    <FaMagnifyingGlassChart /> Entendendo a Tabela
                </button>
            </div>

            <div className="strategy-tab-content">
                {activeTab === 'qualificacao' && (
                    <div className="tab-pane fade-in">
                        <div className="info-intro-card">
                            <h3 className="icon-inline"><FaGears /> Como a IA avalia as oportunidades</h3>
                            <p>
                                Nosso motor institucional roda <strong>dois modelos de Inteligência Artificial diferentes</strong> para qualificar 
                                as oportunidades do mercado. Para cada modelo (Direcional ou de Contra-Tendência), ele aplica critérios 
                                específicos de Vetos (risco inaceitável) e Pontuação (0 a 100).
                            </p>
                        </div>

                        <div className="models-wrapper">
                            <h3 style={{ marginTop: '16px', marginBottom: '16px', color: 'var(--accent-blue)', fontSize: '1.05rem' }}>
                                Modelo 1: Lógica Direcional (Pegar a Taxa)
                            </h3>
                            <div className="qualification-grid">
                                <div className="qual-card vetos">
                                    <div className="qual-card-header">
                                        <div className="icon-wrap warning"><FaShieldHalved /></div>
                                        <h4>Filtros de Proteção (Vetos)</h4>
                                    </div>
                                    <p className="qual-desc">Moedas recebem nota 0 (ZERO) se caírem nestes critérios de alto risco:</p>
                                    <ul className="qual-list highlight-red">
                                        <li><strong>Risco de Squeeze (Volatilidade Extrema):</strong> Rejeita moedas com variação de preço de ±35% nas últimas 24h. A chance de ser liquidado caçando taxa não compensa.</li>
                                        <li><strong>Risco de Slippage (Baixíssima Liquidez):</strong> Rejeita volume intradiário menor que US$ 2M a 5M.</li>
                                    </ul>
                                </div>

                                <div className="qual-card score">
                                    <div className="qual-card-header">
                                        <div className="icon-wrap success"><FaChartLine /></div>
                                        <h4>Sistema de Pontuação (0-100)</h4>
                                    </div>
                                    <p className="qual-desc">Pilares que dão pontos à estratégia Direcional:</p>
                                    <ul className="qual-list">
                                        <li><strong>APY Líquido (Até 40 pts):</strong> Desconta as taxas da corretora (Fee Taker/Maker). Ideal &gt; 40%/ano bruto.</li>
                                        <li><strong>Liquidez de Mercado (Até 20 pts):</strong> Quanto maior o volume, mais fácil entrar/sair (ex: &gt; US$ 300M).</li>
                                        <li><strong>Consistência Histórica (Até 15 pts):</strong> Checa pagamentos dos <strong>últimos 3 dias (15 ciclos)</strong> na mesma direção. Oscilações perdem pontos.</li>
                                        <li><strong>Intervalo Menor (Até 10 pts):</strong> Bônus para moedas que pagam Funding em intervalos de 1h, 2h ou 4h.</li>
                                    </ul>
                                </div>
                            </div>
                            
                            <h3 style={{ marginTop: '32px', marginBottom: '16px', color: 'var(--accent-purple)', fontSize: '1.05rem' }}>
                                Modelo 2: Lógica de Contra-Tendência
                            </h3>
                            <div className="qualification-grid" style={{ marginBottom: '12px' }}>
                                <div className="qual-card vetos">
                                    <div className="qual-card-header">
                                        <div className="icon-wrap warning" style={{ backgroundColor: 'rgba(251, 191, 36, 0.15)', color: 'var(--accent-yellow)' }}><FaShieldHalved /></div>
                                        <h4>Critérios Excludentes</h4>
                                    </div>
                                    <p className="qual-desc">Por ser uma aposta de reversão, as regras são diferentes:</p>
                                    <ul className="qual-list highlight-red">
                                        <li><strong>Taxa Irrelevante (Baixa distorção):</strong> Vetado se o funding estiver muito baixo (&lt; 0.01%). Não há sinal de distorção extrema ou pânico para reverter.</li>
                                        <li><strong>Incapacidade de Saída (Falta de Liquidez):</strong> Vetado se volume for menor que US$ 2M (sem dinheiro para saídas rápidas no squeeze).</li>
                                    </ul>
                                </div>

                                <div className="qual-card score" style={{ borderColor: 'rgba(168, 85, 247, 0.3)' }}>
                                    <div className="qual-card-header">
                                        <div className="icon-wrap success" style={{ backgroundColor: 'rgba(168, 85, 247, 0.15)', color: 'var(--accent-purple)' }}><FaBrain /></div>
                                        <h4>Avaliador de Saturação (0-100)</h4>
                                    </div>
                                    <p className="qual-desc">Pilares que dão pontos à estratégia de Contra-Tendência:</p>
                                    <ul className="qual-list">
                                        <li><strong>Extremidade da Taxa (Até 40 pts):</strong> Quanto mais distorcida/extrema a taxa original (&gt; 0.15%), mais forte o sinal de reversão.</li>
                                        <li><strong>Persistência Insustentável (Até 30 pts):</strong> Verifica <strong>5 dias (até 20 ciclos)</strong> diretos de taxa pagando no mesmo sentido sinalizando que a maior parte do mercado está saturada em uma única direção.</li>
                                        <li><strong>Liquidez Absorvida (Até 20 pts):</strong> Beneficia volumes massivos para absorver a reversão forte de tendência.</li>
                                        <li><strong>Bônus de Volatilidade (Até 10 pts):</strong> Ao contrário do direcional, volatilidade agressiva não veta aqui, ela dá BÔNUS pois favorece reversões drásticas de tendência.</li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <div className="confidence-levels">
                            <h4>Interpretando o Sinal de Confiança</h4>
                            <div className="levels-container">
                                <div className="level-item strong">
                                    <span className="level-badge">FORTE (75+ pts)</span>
                                    <p>As melhores oportunidades do mercado. Alta liquidez, APY consistente e volatilidade controlada. Sinal verde para a IA operar.</p>
                                </div>
                                <div className="level-item moderate">
                                    <span className="level-badge">MODERADO (50 a 74 pts)</span>
                                    <p>Boas oportunidades secundárias. O APY pode ser um pouco menor ou o volume não ser de uma Top 10, mas ainda seguras para operação.</p>
                                </div>
                                <div className="level-item weak">
                                    <span className="level-badge">FRACO / EVITAR (&lt; 50 pts)</span>
                                    <p>O risco não compensa o retorno. A IA recomenda Evitar a entrada automática nestes ativos.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'estrategias' && (
                    <div className="tab-pane fade-in">
                        <div className="strategy-grid">
                            {STRATEGIES.map(strat => (
                                <div
                                    key={strat.id}
                                    className={`strategy-card ${expanded === strat.id ? 'expanded' : ''}`}
                                    onClick={() => setExpanded(expanded === strat.id ? null : strat.id)}
                                >
                                    <div className="strategy-card-top">
                                        <div className="strategy-card-header">
                                            <span className="strategy-icon">{strat.icon}</span>
                                            <div>
                                                <h3>{strat.name}</h3>
                                                <span className="strategy-risk" style={{ color: strat.riskColor }}>
                                                    Risco: {strat.risk}
                                                </span>
                                            </div>
                                        </div>
                                        <p className="strategy-desc">{strat.description}</p>
                                    </div>

                                    {expanded === strat.id && (
                                        <div className="strategy-details">
                                            <div className="strategy-section">
                                                <h4 className="icon-inline">
                                                    <FaMapPin aria-hidden="true" />
                                                    Como fazer
                                                </h4>
                                                <ol>
                                                    {strat.how.map((step, i) => (
                                                        <li key={i}>{step}</li>
                                                    ))}
                                                </ol>
                                            </div>

                                            <div className="strategy-pros-cons">
                                                <div className="strategy-section pros">
                                                    <h4 className="icon-inline">
                                                        <FaCircleCheck aria-hidden="true" />
                                                        Vantagens
                                                    </h4>
                                                    <ul>
                                                        {strat.pros.map((p, i) => <li key={i}>{p}</li>)}
                                                    </ul>
                                                </div>
                                                <div className="strategy-section cons">
                                                    <h4 className="icon-inline">
                                                        <FaTriangleExclamation aria-hidden="true" />
                                                        Desvantagens
                                                    </h4>
                                                    <ul>
                                                        {strat.cons.map((c, i) => <li key={i}>{c}</li>)}
                                                    </ul>
                                                </div>
                                            </div>

                                            <div className="strategy-tip">
                                                <FaLightbulb aria-hidden="true" />
                                                <strong>Dica:</strong> {strat.tip}
                                            </div>
                                        </div>
                                    )}

                                    <div className="strategy-expand-hint">
                                        {expanded === strat.id ? 'Clique para fechar ▲' : 'Clique para ver detalhes ▼'}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {activeTab === 'tabela' && (
                    <div className="tab-pane fade-in">
                        <div className="strategy-legend expanded-legend">
                            <h3 className="icon-inline">
                                <FaMagnifyingGlassChart aria-hidden="true" />
                                Como ler os dados operacionais
                            </h3>
                            <p className="legend-p">
                                Compreender os indicadores visuais é essencial para o acompanhamento manual das suas operações.
                            </p>
                            <div className="legend-items vertical-layout">
                                <div className="legend-item bg-card-style">
                                    <span className="direction-badge dir-short">
                                        <FaCircle aria-hidden="true" /> SHORT
                                    </span>
                                    <div>
                                        <strong>Quando operar SHORT?</strong>
                                        <span>Funding positivo — Maioria está comprando (Long), corretora cobra deles para pagar quem Vendar (Short).</span>
                                    </div>
                                </div>
                                <div className="legend-item bg-card-style">
                                    <span className="direction-badge dir-long">
                                        <FaCircle aria-hidden="true" /> LONG
                                    </span>
                                    <div>
                                        <strong>Quando operar LONG?</strong>
                                        <span>Funding negativo — Maioria vendendo a descoberto (Short), corretora paga os Compradores (Long).</span>
                                    </div>
                                </div>
                                <div className="legend-item bg-card-style shrink">
                                    <span className="legend-profit">+0.05%</span>
                                    <div>
                                        <strong>Expectativa de Lucro por Ciclo</strong>
                                        <span>Lucro estimado que você recebe a cada pagamento de funding (ex: a cada 8h ou 4h, dependendo da moeda).</span>
                                    </div>
                                </div>
                                <div className="legend-item bg-card-style shrink">
                                    <span className="legend-monthly">+4.56%</span>
                                    <div>
                                        <strong>Projeção de Rendimento Mensal (APY Mensal)</strong>
                                        <span>Projeção mensal estimada caso a taxa se mantenha constante pelos próximos 30 dias. Serve como referência de rentabilidade.</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
