
import os
import sqlite3
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, flash
from markupsafe import escape

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")

# Banco separado para evitar conflitos com versões anteriores
DB = os.environ.get("DATABASE_PATH", "boletim_personalizado.db")

PONTOS_TRIMESTRES = {1: 30, 2: 40, 3: 30}
MEDIA_APROVACAO = 70

AVALIACOES_PADRAO = [
    "Prova objetiva",
    "Prova discursiva",
    "Simulado",
    "Atividade",
    "Qualitativo"
]

MATERIAS_PADRAO = [
    "Português", "Redação", "Inglês", "Matemática",
    "Física", "Química", "Biologia", "História",
    "Geografia", "Filosofia", "Sociologia"
]


def conectar():
    banco = sqlite3.connect(DB)
    banco.row_factory = sqlite3.Row
    return banco


def iniciar_banco():
    with conectar() as banco:
        banco.execute("""
            CREATE TABLE IF NOT EXISTS materias_app (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            )
        """)

        banco.execute("""
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_id INTEGER NOT NULL,
                trimestre INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                nota REAL,
                valor REAL DEFAULT 0,
                FOREIGN KEY (materia_id) REFERENCES materias_app(id),
                UNIQUE(materia_id, trimestre, categoria)
            )
        """)

        banco.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes_app (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                aluno TEXT DEFAULT '',
                escola TEXT DEFAULT '',
                ano TEXT DEFAULT ''
            )
        """)

        banco.execute("""
            INSERT OR IGNORE INTO configuracoes_app
            (id, aluno, escola, ano)
            VALUES (1, '', '', '2026')
        """)

        for nome in MATERIAS_PADRAO:
            banco.execute(
                "INSERT OR IGNORE INTO materias_app (nome) VALUES (?)",
                (nome,)
            )

        materias = banco.execute(
            "SELECT id FROM materias_app"
        ).fetchall()

        for materia in materias:
            for trimestre in (1, 2, 3):
                for categoria in AVALIACOES_PADRAO:
                    banco.execute("""
                        INSERT OR IGNORE INTO lancamentos
                        (materia_id, trimestre, categoria, nota, valor)
                        VALUES (?, ?, ?, NULL, 0)
                    """, (materia["id"], trimestre, categoria))


iniciar_banco()


def obter_config():
    with conectar() as banco:
        return banco.execute(
            "SELECT * FROM configuracoes_app WHERE id = 1"
        ).fetchone()


BASE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }} | Meu Boletim</title>
<style>
:root {
    --fundo:#f4f6fb; --card:#ffffff; --texto:#172033;
    --muted:#758096; --azul:#4f46e5; --borda:#e8eaf1;
    --verde:#16a36a; --vermelho:#dc4444;
}
* { box-sizing:border-box; }
body {
    margin:0; background:var(--fundo); color:var(--texto);
    font-family:Inter,Arial,sans-serif;
}
header {
    background:#171b35; color:white; padding:22px 6%;
    display:flex; justify-content:space-between; align-items:center;
    gap:15px; flex-wrap:wrap;
}
header h1 { margin:0; font-size:22px; }
header span { color:#c4c8df; font-size:13px; }
nav {
    background:white; padding:13px 6%; display:flex;
    gap:20px; border-bottom:1px solid var(--borda); flex-wrap:wrap;
}
nav a { color:#596078; text-decoration:none; font-weight:600; font-size:14px; }
nav a:hover { color:var(--azul); }
main { max-width:1150px; margin:30px auto; padding:0 18px; }
h2 { margin-top:0; font-size:23px; }
h3 { font-size:17px; }
.muted { color:var(--muted); font-size:13px; }
.grid {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
    gap:15px; margin:20px 0;
}
.card {
    background:var(--card); border:1px solid var(--borda);
    border-radius:15px; padding:20px; margin-bottom:18px;
}
.numero { font-size:27px; font-weight:800; margin:9px 0; }
.progress {
    height:9px; background:#eceef5; border-radius:20px;
    overflow:hidden; margin-top:12px;
}
.progress div { height:100%; background:var(--azul); border-radius:20px; }
.tabs { display:flex; gap:9px; flex-wrap:wrap; margin:20px 0; }
.tabs a {
    text-decoration:none; padding:10px 16px; border-radius:9px;
    background:white; border:1px solid var(--borda); color:var(--texto);
    font-weight:600; font-size:13px;
}
.tabs a.ativo { background:var(--azul); color:white; }
table { width:100%; border-collapse:collapse; }
th,td { padding:12px 9px; text-align:left; border-bottom:1px solid var(--borda); }
th { font-size:12px; color:var(--muted); }
td { font-size:14px; }
input {
    width:100%; padding:11px; border:1px solid #dfe2eb;
    border-radius:8px; outline:none; background:white;
}
input:focus { border-color:var(--azul); }
.botao {
    border:0; border-radius:9px; padding:11px 16px;
    background:var(--azul); color:white; font-weight:700;
    cursor:pointer; text-decoration:none; display:inline-block;
}
.botao:hover { opacity:.9; }
.botao-sec { background:#eceeff; color:var(--azul); }
.linha-form {
    display:grid; grid-template-columns:1fr 110px 110px 90px;
    gap:10px; align-items:center; margin:12px 0;
}
.nome-avaliacao { font-weight:600; font-size:14px; }
.etiqueta {
    display:inline-block; padding:6px 10px; border-radius:20px;
    font-size:12px; font-weight:700; background:#eef0ff; color:var(--azul);
}
.ok { color:var(--verde); font-weight:700; }
.erro { color:var(--vermelho); font-weight:700; }
.flash {
    background:#fff3d7; padding:13px; border-radius:9px;
    margin-bottom:15px; font-size:14px;
}
@media(max-width:650px) {
    .linha-form { grid-template-columns:1fr 1fr; }
    .linha-form .nome-avaliacao { grid-column:1/-1; }
    table { font-size:12px; }
    th,td { padding:9px 5px; }
}
</style>
</head>
<body>
<header>
    <div>
        <h1>Meu Boletim</h1>
        <span>Seu desempenho escolar em um só lugar</span>
    </div>
    <div>{{ config.aluno or 'Área do estudante' }}</div>
</header>
<nav>
    <a href="/">Painel</a>
    <a href="/relatorio">Relatório anual</a>
    <a href="/configuracoes">Configurações</a>
</nav>
<main>
{% with mensagens = get_flashed_messages() %}
    {% for mensagem in mensagens %}
        <div class="flash">{{ mensagem }}</div>
    {% endfor %}
{% endwith %}
{{ conteudo|safe }}
</main>
</body>
</html>
"""


PAINEL = """
<h2>Olá, {{ config.aluno or 'estudante' }}!</h2>
<p class="muted">Acompanhe suas notas e seu desempenho escolar.</p>

<div class="grid">
    <div class="card">
        <span class="muted">Total do ano</span>
        <div class="numero">{{ "%.1f"|format(total_geral) }} / 100</div>
        <div class="progress"><div style="width:{{ [total_geral,100]|min }}%"></div></div>
    </div>
    <div class="card">
        <span class="muted">Meta para aprovação</span>
        <div class="numero">70 pontos</div>
        <span class="muted">Média anual necessária</span>
    </div>
    <div class="card">
        <span class="muted">Situação geral</span>
        <div class="numero" style="font-size:21px">
        {% if total_geral >= 70 %}
            <span class="ok">Aprovado</span>
        {% else %}
            <span class="erro">Em andamento</span>
        {% endif %}
        </div>
        <span class="muted">Resultado considerando as notas lançadas</span>
    </div>
</div>

<div class="tabs">
    {% for n in [1,2,3] %}
    <a class="{{ 'ativo' if periodo == n else '' }}" href="/?trimestre={{ n }}">
        {{ n }}º trimestre
    </a>
    {% endfor %}
    <a class="{{ 'ativo' if periodo == 4 else '' }}" href="/?trimestre=4">Ano completo</a>
</div>

{% if periodo != 4 %}
<div class="card">
    <h3>{{ periodo }}º trimestre</h3>
    <p class="muted">Este trimestre vale {{ limite }} pontos. Preencha somente sua nota e o valor total de cada avaliação.</p>
    <div class="grid">
        <div>
            <span class="muted">Pontos lançados</span>
            <div class="numero">{{ "%.1f"|format(total_periodo) }} / {{ limite }}</div>
        </div>
        <div>
            <span class="muted">Valor das avaliações cadastradas</span>
            <div class="numero">{{ "%.1f"|format(valor_periodo) }} / {{ limite }}</div>
        </div>
    </div>
</div>

{% for materia in materias %}
<div class="card">
    <h3>{{ materia.nome }}</h3>
    <div class="grid">
        <div>
            <span class="muted">Sua pontuação</span>
            <div class="numero">{{ "%.1f"|format(materia.pontos) }} / {{ limite }}</div>
        </div>
        <div>
            <span class="muted">Pontos possíveis cadastrados</span>
            <div class="numero">{{ "%.1f"|format(materia.valor) }} / {{ limite }}</div>
        </div>
    </div>
    <div class="progress">
        <div style="width:{{ [materia.pontos / limite * 100,100]|min }}%"></div>
    </div>

    <form method="POST" action="/salvar">
        <input type="hidden" name="materia_id" value="{{ materia.id }}">
        <input type="hidden" name="trimestre" value="{{ periodo }}">
        {% for avaliacao in materia.avaliacoes %}
        <div class="linha-form">
            <div class="nome-avaliacao">{{ avaliacao.categoria }}</div>
            <div>
                <label class="muted">Sua nota</label>
                <input type="number" name="nota_{{ avaliacao.id }}"
                    min="0" step="0.01" max="100"
                    value="{{ '' if avaliacao.nota is none else avaliacao.nota }}"
                    placeholder="Nota">
            </div>
            <div>
                <label class="muted">Valor total</label>
                <input type="number" name="valor_{{ avaliacao.id }}"
                    min="0" step="0.01" max="{{ limite }}"
                    value="{{ avaliacao.valor if avaliacao.valor else '' }}"
                    placeholder="Ex.: 6">
            </div>
            <div>
                <button class="botao" type="submit">Salvar</button>
            </div>
        </div>
        {% endfor %}
    </form>
</div>
{% endfor %}

{% else %}
<h3>Resultado por matéria</h3>
{% for materia in materias %}
<div class="card">
    <h3>{{ materia.nome }}</h3>
    <div class="numero">{{ "%.1f"|format(materia.pontos) }} / 100</div>
    <div class="progress">
        <div style="width:{{ [materia.pontos,100]|min }}%"></div>
    </div>
    <p class="muted">
        1º trimestre: {{ "%.1f"|format(materia.trimestres[1]) }}/30
        &nbsp; | &nbsp;
        2º trimestre: {{ "%.1f"|format(materia.trimestres[2]) }}/40
        &nbsp; | &nbsp;
        3º trimestre: {{ "%.1f"|format(materia.trimestres[3]) }}/30
    </p>
    {% if materia.pontos >= 70 %}
        <span class="ok">Aprovado</span>
    {% else %}
        <span class="erro">Ainda não atingiu 70 pontos</span>
    {% endif %}
</div>
{% endfor %}
{% endif %}
"""


RELATORIO = """
<h2>Relatório anual</h2>
<p class="muted">Veja o resultado de cada matéria ao longo do ano.</p>
<div class="card">
<table>
<tr>
<th>Matéria</th><th>1º tri.</th><th>2º tri.</th>
<th>3º tri.</th><th>Total</th><th>Situação</th>
</tr>
{% for m in materias %}
<tr>
<td><b>{{ m.nome }}</b></td>
<td>{{ "%.1f"|format(m.trimestres[1]) }}/30</td>
<td>{{ "%.1f"|format(m.trimestres[2]) }}/40</td>
<td>{{ "%.1f"|format(m.trimestres[3]) }}/30</td>
<td><b>{{ "%.1f"|format(m.pontos) }}/100</b></td>
<td>
{% if m.pontos >= 70 %}
<span class="ok">Aprovado</span>
{% else %}
<span class="erro">Em andamento</span>
{% endif %}
</td>
</tr>
{% endfor %}
</table>
</div>
<div class="card">
<h3>Resultado geral</h3>
<div class="numero">{{ "%.1f"|format(total_geral) }} / 100</div>
<p class="muted">A meta de aprovação é 70 pontos em cada matéria.</p>
</div>
"""


CONFIGURACOES = """
<h2>Configurações</h2>
<div class="card">
<form method="POST">
    <p><label>Nome do estudante</label>
    <input name="aluno" value="{{ config.aluno or '' }}" placeholder="Seu nome"></p>
    <p><label>Nome da escola</label>
    <input name="escola" value="{{ config.escola or '' }}" placeholder="Sua escola"></p>
    <p><label>Ano letivo</label>
    <input name="ano" value="{{ config.ano or '2026' }}"></p>
    <button class="botao" type="submit">Salvar configurações</button>
</form>
</div>
<div class="card">
<h3>Distribuição de pontos</h3>
<p>1º trimestre: <b>30 pontos</b></p>
<p>2º trimestre: <b>40 pontos</b></p>
<p>3º trimestre: <b>30 pontos</b></p>
<p>Média anual para aprovação: <b>70 pontos</b></p>
</div>
"""


def carregar_materias():
    resultado = []
    with conectar() as banco:
        materias = banco.execute(
            "SELECT * FROM materias_app ORDER BY nome"
        ).fetchall()

        for materia in materias:
            trimestres = {}
            total_ano = 0

            for trimestre in (1, 2, 3):
                linhas = banco.execute("""
                    SELECT * FROM lancamentos
                    WHERE materia_id = ? AND trimestre = ?
                    ORDER BY id
                """, (materia["id"], trimestre)).fetchall()

                pontos = sum(
                    float(a["nota"] or 0) for a in linhas
                )
                valor = sum(float(a["valor"] or 0) for a in linhas)

                trimestres[trimestre] = pontos
                total_ano += pontos

                if trimestre == periodo_atual:
                    pass

                if trimestre == 1:
                    pass

            resultado.append({
                "id": materia["id"],
                "nome": materia["nome"],
                "pontos": total_ano,
                "trimestres": trimestres
            })

    return resultado


def renderizar(template, titulo="Meu Boletim", **dados):
    config = obter_config()
    conteudo = render_template_string(
        template, config=config, **dados
    )
    return render_template_string(
        BASE, conteudo=conteudo, titulo=titulo, config=config
    )


@app.route("/")
def inicio():
    try:
        periodo = int(request.args.get("trimestre", 1))
    except ValueError:
        periodo = 1

    if periodo not in (1, 2, 3, 4):
        periodo = 1

    materias = carregar_materias()
    total_geral = sum(m["pontos"] for m in materias) / max(len(materias), 1)

    limite = PONTOS_TRIMESTRES.get(periodo, 100)
    total_periodo = 0
    valor_periodo = 0

    with conectar() as banco:
        for materia in materias:
            if periodo == 4:
                materia["avaliacoes"] = []
                continue

            linhas = banco.execute("""
                SELECT * FROM lancamentos
                WHERE materia_id = ? AND trimestre = ?
                ORDER BY id
            """, (materia["id"], periodo)).fetchall()

            materia["avaliacoes"] = linhas
            materia["pontos"] = sum(float(a["nota"] or 0) for a in linhas)
            materia["valor"] = sum(float(a["valor"] or 0) for a in linhas)

            total_periodo += materia["pontos"]
            valor_periodo += materia["valor"]

    if periodo == 4:
        for materia in materias:
            materia["pontos"] = sum(materia["trimestres"].values())

    return renderizar(
        PAINEL, "Painel",
        materias=materias,
        periodo=periodo,
        limite=limite,
        total_geral=total_geral,
        total_periodo=total_periodo,
        valor_periodo=valor_periodo
    )


@app.route("/salvar", methods=["POST"])
def salvar():
    try:
        materia_id = int(request.form["materia_id"])
        trimestre = int(request.form["trimestre"])
    except (ValueError, KeyError):
        flash("Dados inválidos.")
        return redirect(url_for("inicio"))

    if trimestre not in PONTOS_TRIMESTRES:
        flash("Trimestre inválido.")
        return redirect(url_for("inicio"))

    with conectar() as banco:
        linhas = banco.execute("""
            SELECT * FROM lancamentos
            WHERE materia_id = ? AND trimestre = ?
        """, (materia_id, trimestre)).fetchall()

        if not linhas:
            flash("Matéria não encontrada.")
            return redirect(url_for("inicio", trimestre=trimestre))

        novos_valores = []
        soma_valores = 0

        for avaliacao in linhas:
            id_av = avaliacao["id"]
            nota_texto = request.form.get(f"nota_{id_av}", "").strip()
            valor_texto = request.form.get(f"valor_{id_av}", "").strip()

            try:
                nota = float(nota_texto) if nota_texto else None
                valor = float(valor_texto) if valor_texto else 0
            except ValueError:
                flash("Digite somente números nas notas e nos valores.")
                return redirect(url_for("inicio", trimestre=trimestre))

            if valor < 0 or (nota is not None and nota < 0):
                flash("Não é permitido usar valores negativos.")
                return redirect(url_for("inicio", trimestre=trimestre))

            if nota is not None and nota > valor:
                flash(f"A nota de {avaliacao['categoria']} não pode ser maior que o valor total.")
                return redirect(url_for("inicio", trimestre=trimestre))

            soma_valores += valor
            novos_valores.append((id_av, nota, valor))

        limite = PONTOS_TRIMESTRES[trimestre]

        if soma_valores > limite + 0.001:
            flash(f"A soma dos valores das avaliações não pode passar de {limite} pontos.")
            return redirect(url_for("inicio", trimestre=trimestre))

        for id_av, nota, valor in novos_valores:
            banco.execute("""
                UPDATE lancamentos
                SET nota = ?, valor = ?
                WHERE id = ?
            """, (nota, valor, id_av))

    flash("Notas salvas com sucesso!")
    return redirect(url_for("inicio", trimestre=trimestre))


@app.route("/relatorio")
def relatorio():
    materias = carregar_materias()
    total_geral = sum(m["pontos"] for m in materias) / max(len(materias), 1)
    return renderizar(
        RELATORIO, "Relatório anual",
        materias=materias,
        total_geral=total_geral
    )


@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    if request.method == "POST":
        with conectar() as banco:
            banco.execute("""
                UPDATE configuracoes_app
                SET aluno = ?, escola = ?, ano = ?
                WHERE id = 1
            """, (
                request.form.get("aluno", "").strip(),
                request.form.get("escola", "").strip(),
                request.form.get("ano", "").strip()
            ))
        flash("Configurações salvas!")
        return redirect(url_for("configuracoes"))

    return renderizar(CONFIGURACOES, "Configurações")


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
