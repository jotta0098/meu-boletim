
import os
import csv
import io
import sqlite3
import logging
from pathlib import Path
from flask import (
    Flask, request, redirect, url_for,
    render_template_string, flash, Response
)

# ==================================================
# CONFIGURAÇÃO
# ==================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "meu-boletim-chave-local")
app.logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "boletim.db")))

PONTOS_TRIMESTRES = {
    1: 30,
    2: 40,
    3: 30
}

MEDIA_APROVACAO = 70

MATERIAS_INICIAIS = [
    "Português", "Redação", "Inglês", "Matemática",
    "Física", "Química", "Biologia", "História",
    "Geografia", "Filosofia", "Sociologia"
]


# ==================================================
# BANCO DE DADOS
# ==================================================

def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(DB_PATH), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    return db


def iniciar_banco():
    with conectar() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                aluno TEXT NOT NULL DEFAULT 'Meu Boletim',
                escola TEXT DEFAULT '',
                ano INTEGER DEFAULT 2026,
                tema TEXT DEFAULT 'escuro'
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                professor TEXT DEFAULT '',
                cor TEXT DEFAULT '#3b82f6'
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS avaliacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_id INTEGER NOT NULL,
                trimestre INTEGER NOT NULL,
                nome TEXT NOT NULL,
                nota REAL NOT NULL DEFAULT 0,
                valor REAL NOT NULL DEFAULT 0,
                data TEXT DEFAULT '',
                FOREIGN KEY(materia_id)
                    REFERENCES materias(id)
                    ON DELETE CASCADE
            )
        """)

        db.execute("""
            INSERT OR IGNORE INTO configuracoes
            (id, aluno, escola, ano, tema)
            VALUES (1, 'Meu Boletim', '', 2026, 'escuro')
        """)

        for nome in MATERIAS_INICIAIS:
            db.execute("""
                INSERT OR IGNORE INTO materias (nome)
                VALUES (?)
            """, (nome,))


iniciar_banco()


# ==================================================
# FUNÇÕES AUXILIARES
# ==================================================

def obter_configuracoes():
    with conectar() as db:
        return db.execute("""
            SELECT * FROM configuracoes WHERE id = 1
        """).fetchone()


def obter_materias():
    with conectar() as db:
        return db.execute("""
            SELECT * FROM materias ORDER BY nome
        """).fetchall()


def obter_avaliacoes(materia_id, trimestre):
    with conectar() as db:
        return db.execute("""
            SELECT * FROM avaliacoes
            WHERE materia_id = ? AND trimestre = ?
            ORDER BY id
        """, (materia_id, trimestre)).fetchall()


def calcular_trimestre(materia_id, trimestre):
    avaliacoes = obter_avaliacoes(materia_id, trimestre)

    pontos = sum(a["nota"] for a in avaliacoes)
    valor_cadastrado = sum(a["valor"] for a in avaliacoes)

    limite = PONTOS_TRIMESTRES[trimestre]
    restante = max(0, limite - valor_cadastrado)

    return {
        "avaliacoes": avaliacoes,
        "pontos": pontos,
        "valor_cadastrado": valor_cadastrado,
        "limite": limite,
        "restante": restante
    }


def calcular_final(materia_id):
    trimestres = {}

    total_pontos = 0

    for trimestre in (1, 2, 3):
        resultado = calcular_trimestre(materia_id, trimestre)

        trimestres[trimestre] = resultado
        total_pontos += resultado["pontos"]

    percentual = total_pontos

    if total_pontos >= MEDIA_APROVACAO:
        situacao = "Aprovado"
    else:
        situacao = "Abaixo da média"

    return {
        "trimestres": trimestres,
        "pontos": total_pontos,
        "possivel": 100,
        "percentual": percentual,
        "faltam": max(0, MEDIA_APROVACAO - total_pontos),
        "situacao": situacao
    }


def renderizar(conteudo, titulo="Meu Boletim"):
    config = obter_configuracoes()

    return render_template_string(
        BASE_HTML,
        conteudo=conteudo,
        titulo=titulo,
        config=config
    )


def voltar(trimestre=1):
    return redirect(url_for("inicio", periodo=trimestre))


# ==================================================
# PAINEL PRINCIPAL
# ==================================================

@app.route("/")
def inicio():
    config = obter_configuracoes()

    periodo = request.args.get("periodo", "1")
    pesquisa = request.args.get("q", "").strip()

    if periodo not in ("1", "2", "3", "final"):
        periodo = "1"

    materias = obter_materias()
    dados = []

    total_pontos = 0
    total_possivel = 0

    aprovadas = 0
    abaixo_media = 0

    for materia in materias:

        if pesquisa and pesquisa.lower() not in materia["nome"].lower():
            continue

        if periodo == "final":

            resultado = calcular_final(materia["id"])

            dados.append({
                "materia": materia,
                **resultado
            })

            total_pontos += resultado["pontos"]
            total_possivel += 100

            if resultado["situacao"] == "Aprovado":
                aprovadas += 1
            else:
                abaixo_media += 1

        else:

            trimestre = int(periodo)

            resultado = calcular_trimestre(
                materia["id"], trimestre
            )

            dados.append({
                "materia": materia,
                **resultado
            })

            total_pontos += resultado["pontos"]
            total_possivel += resultado["limite"]

    percentual_geral = (
        total_pontos / total_possivel * 100
        if total_possivel else 0
    )

    geral = {
        "pontos": total_pontos,
        "possivel": total_possivel,
        "percentual": percentual_geral,
        "aprovadas": aprovadas,
        "abaixo_media": abaixo_media,
        "total": len(dados)
    }

    return renderizar(
        render_template_string(
            PAINEL,
            dados=dados,
            geral=geral,
            periodo=periodo,
            pesquisa=pesquisa,
            media=MEDIA_APROVACAO
        ),
        "Painel | Meu Boletim"
    )


# ==================================================
# ADICIONAR MATÉRIA
# ==================================================

@app.route("/materia/adicionar", methods=["POST"])
def adicionar_materia():

    nome = request.form.get("nome", "").strip()
    professor = request.form.get("professor", "").strip()
    cor = request.form.get("cor", "#3b82f6")

    if not nome:
        flash("Digite o nome da matéria.")
        return voltar()

    try:
        with conectar() as db:
            db.execute("""
                INSERT INTO materias (nome, professor, cor)
                VALUES (?, ?, ?)
            """, (nome, professor, cor))

        flash("Matéria adicionada com sucesso!")

    except sqlite3.IntegrityError:
        flash("Essa matéria já existe.")

    except Exception:
        app.logger.exception("Erro ao adicionar matéria")
        flash("Erro ao adicionar matéria.")

    return voltar()


# ==================================================
# EDITAR MATÉRIA
# ==================================================

@app.route("/materia/<int:materia_id>/editar", methods=["POST"])
def editar_materia(materia_id):

    nome = request.form.get("nome", "").strip()
    professor = request.form.get("professor", "").strip()
    cor = request.form.get("cor", "#3b82f6")

    if not nome:
        flash("O nome da matéria é obrigatório.")
        return voltar()

    try:
        with conectar() as db:
            db.execute("""
                UPDATE materias
                SET nome = ?, professor = ?, cor = ?
                WHERE id = ?
            """, (nome, professor, cor, materia_id))

        flash("Matéria atualizada!")

    except sqlite3.IntegrityError:
        flash("Já existe uma matéria com esse nome.")

    except Exception:
        app.logger.exception("Erro ao editar matéria")
        flash("Não foi possível editar a matéria.")

    return voltar()


# ==================================================
# EXCLUIR MATÉRIA
# ==================================================

@app.route("/materia/<int:materia_id>/excluir", methods=["POST"])
def excluir_materia(materia_id):

    try:
        with conectar() as db:
            db.execute(
                "DELETE FROM avaliacoes WHERE materia_id = ?",
                (materia_id,)
            )

            db.execute(
                "DELETE FROM materias WHERE id = ?",
                (materia_id,)
            )

        flash("Matéria excluída.")

    except Exception:
        app.logger.exception("Erro ao excluir matéria")
        flash("Não foi possível excluir a matéria.")

    return voltar()


# ==================================================
# ADICIONAR AVALIAÇÃO
# ==================================================

@app.route("/avaliacao/adicionar", methods=["POST"])
def adicionar_avaliacao():

    try:
        materia_id = int(request.form["materia_id"])
        trimestre = int(request.form["trimestre"])

        nome = request.form.get("nome", "").strip()
        nota = float(request.form["nota"].replace(",", "."))
        valor = float(request.form["valor"].replace(",", "."))
        data = request.form.get("data", "")

        if trimestre not in PONTOS_TRIMESTRES:
            raise ValueError("Trimestre inválido.")

        if not nome:
            raise ValueError("Nome obrigatório.")

        if valor <= 0 or nota < 0 or nota > valor:
            raise ValueError("Nota ou valor inválido.")

        limite = PONTOS_TRIMESTRES[trimestre]

        with conectar() as db:

            materia = db.execute("""
                SELECT id FROM materias WHERE id = ?
            """, (materia_id,)).fetchone()

            if not materia:
                flash("Matéria não encontrada.")
                return voltar(trimestre)

            atual = db.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM avaliacoes
                WHERE materia_id = ? AND trimestre = ?
            """, (materia_id, trimestre)).fetchone()["total"]

            if atual + valor > limite + 0.000001:
                flash(
                    f"Essa matéria permite no máximo {limite} pontos "
                    f"no {trimestre}º trimestre. "
                    f"Você ainda pode cadastrar {max(0, limite-atual):.2f} pontos."
                )
                return voltar(trimestre)

            db.execute("""
                INSERT INTO avaliacoes
                (materia_id, trimestre, nome, nota, valor, data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (materia_id, trimestre, nome, nota, valor, data))

        flash("Avaliação cadastrada com sucesso!")

    except (ValueError, KeyError):
        flash("Confira os dados digitados.")

    except Exception:
        app.logger.exception("Erro ao adicionar avaliação")
        flash("Erro ao cadastrar avaliação.")

    return voltar(trimestre if "trimestre" in locals() else 1)


# ==================================================
# EDITAR AVALIAÇÃO
# ==================================================

@app.route("/avaliacao/<int:avaliacao_id>/editar", methods=["POST"])
def editar_avaliacao(avaliacao_id):

    try:
        nome = request.form.get("nome", "").strip()
        nota = float(request.form["nota"].replace(",", "."))
        valor = float(request.form["valor"].replace(",", "."))
        data = request.form.get("data", "")

        if not nome or valor <= 0 or nota < 0 or nota > valor:
            raise ValueError()

        with conectar() as db:

            avaliacao = db.execute("""
                SELECT materia_id, trimestre
                FROM avaliacoes WHERE id = ?
            """, (avaliacao_id,)).fetchone()

            if not avaliacao:
                flash("Avaliação não encontrada.")
                return voltar()

            limite = PONTOS_TRIMESTRES[avaliacao["trimestre"]]

            total_outros = db.execute("""
                SELECT COALESCE(SUM(valor), 0) AS total
                FROM avaliacoes
                WHERE materia_id = ?
                AND trimestre = ?
                AND id != ?
            """, (
                avaliacao["materia_id"],
                avaliacao["trimestre"],
                avaliacao_id
            )).fetchone()["total"]

            if total_outros + valor > limite + 0.000001:
                flash("O valor ultrapassa o limite do trimestre.")
                return voltar(avaliacao["trimestre"])

            db.execute("""
                UPDATE avaliacoes
                SET nome = ?, nota = ?, valor = ?, data = ?
                WHERE id = ?
            """, (nome, nota, valor, data, avaliacao_id))

        flash("Avaliação atualizada!")

    except (ValueError, KeyError):
        flash("Confira os valores informados.")

    except Exception:
        app.logger.exception("Erro ao editar avaliação")
        flash("Erro ao atualizar avaliação.")

    return voltar()


# ==================================================
# EXCLUIR AVALIAÇÃO
# ==================================================

@app.route("/avaliacao/<int:avaliacao_id>/excluir", methods=["POST"])
def excluir_avaliacao(avaliacao_id):

    try:
        with conectar() as db:
            db.execute("""
                DELETE FROM avaliacoes WHERE id = ?
            """, (avaliacao_id,))

        flash("Avaliação excluída.")

    except Exception:
        app.logger.exception("Erro ao excluir avaliação")
        flash("Não foi possível excluir a avaliação.")

    return voltar()


# ==================================================
# CONFIGURAÇÕES
# ==================================================

@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes_pagina():

    if request.method == "POST":

        try:
            aluno = request.form.get("aluno", "").strip()
            escola = request.form.get("escola", "").strip()
            ano = int(request.form.get("ano"))
            tema = request.form.get("tema", "escuro")

            if not aluno or ano < 2000 or ano > 2100:
                raise ValueError()

            if tema not in ("escuro", "claro"):
                tema = "escuro"

            with conectar() as db:
                db.execute("""
                    UPDATE configuracoes
                    SET aluno = ?, escola = ?, ano = ?, tema = ?
                    WHERE id = 1
                """, (aluno, escola, ano, tema))

            flash("Configurações salvas!")

        except (ValueError, TypeError):
            flash("Confira as informações.")

        except Exception:
            app.logger.exception("Erro nas configurações")
            flash("Não foi possível salvar.")

        return redirect(url_for("configuracoes_pagina"))

    return renderizar(
        render_template_string(CONFIGURACOES),
        "Configurações | Meu Boletim"
    )


# ==================================================
# RELATÓRIOS
# ==================================================

@app.route("/relatorios")
def relatorios():

    materias = obter_materias()
    linhas = []

    for materia in materias:
        final = calcular_final(materia["id"])

        linhas.append({
            "nome": materia["nome"],
            "final": final
        })

    return renderizar(
        render_template_string(
            RELATORIO,
            linhas=linhas,
            media=MEDIA_APROVACAO
        ),
        "Relatórios | Meu Boletim"
    )


# ==================================================
# EXPORTAR NOTAS
# ==================================================

@app.route("/exportar")
def exportar():

    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")

    escritor.writerow([
        "Matéria",
        "Trimestre",
        "Avaliação",
        "Nota",
        "Valor",
        "Data"
    ])

    with conectar() as db:
        registros = db.execute("""
            SELECT
                m.nome AS materia,
                a.trimestre,
                a.nome AS avaliacao,
                a.nota,
                a.valor,
                a.data
            FROM avaliacoes a
            JOIN materias m ON m.id = a.materia_id
            ORDER BY m.nome, a.trimestre, a.id
        """).fetchall()

    for r in registros:
        escritor.writerow([
            r["materia"],
            r["trimestre"],
            r["avaliacao"],
            r["nota"],
            r["valor"],
            r["data"]
        ])

    return Response(
        "\ufeff" + saida.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=meu_boletim.csv"
        }
    )


# ==================================================
# TESTE DO SERVIDOR
# ==================================================

@app.route("/health")
def health():

    try:
        with conectar() as db:
            db.execute("SELECT 1")

        return {
            "status": "ok",
            "banco": "conectado"
        }

    except Exception:
        app.logger.exception("Erro no banco")
        return {"status": "erro"}, 500


# ==================================================
# INTERFACE VISUAL
# ==================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>{{ titulo }}</title>

<style>
:root {
    --fundo: #0b1120;
    --painel: #151f32;
    --painel2: #1c2940;
    --texto: #f1f5f9;
    --suave: #94a3b8;
    --azul: #3b82f6;
    --borda: #293750;
}

body.claro {
    --fundo: #f1f5f9;
    --painel: #ffffff;
    --painel2: #e2e8f0;
    --texto: #172033;
    --suave: #64748b;
    --borda: #cbd5e1;
}

* { box-sizing: border-box; }

body {
    margin: 0;
    background: var(--fundo);
    color: var(--texto);
    font-family: Arial, sans-serif;
}

header {
    background: var(--painel);
    border-bottom: 1px solid var(--borda);
    padding: 20px 5%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
}

.logo {
    color: var(--azul);
    font-size: 23px;
    font-weight: 800;
}

nav {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}

nav a {
    color: var(--suave);
    text-decoration: none;
    font-size: 14px;
}

nav a:hover { color: var(--azul); }

.container {
    max-width: 1250px;
    margin: auto;
    padding: 30px 18px;
}

h1 { font-size: 29px; }
h2 { font-size: 20px; }

p { color: var(--suave); }

.cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 15px;
    margin: 22px 0;
}

.card, .box {
    background: var(--painel);
    border: 1px solid var(--borda);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 17px;
}

.numero {
    font-size: 29px;
    font-weight: 800;
    margin: 12px 0;
}

.suave {
    color: var(--suave);
    font-size: 13px;
}

.barra {
    background: var(--painel2);
    height: 10px;
    border-radius: 20px;
    overflow: hidden;
}

.barra div {
    height: 100%;
    background: var(--azul);
    border-radius: 20px;
}

.tabs {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 25px 0;
}

.tabs a {
    padding: 13px 18px;
    border-radius: 9px;
    background: var(--painel2);
    color: var(--texto);
    text-decoration: none;
    font-size: 14px;
}

.tabs a.ativo {
    background: var(--azul);
    color: white;
}

input, select {
    padding: 12px;
    border-radius: 8px;
    border: 1px solid var(--borda);
    background: var(--painel2);
    color: var(--texto);
    width: 100%;
    margin: 6px 0 12px;
}

button, .botao {
    border: 0;
    background: var(--azul);
    color: white;
    border-radius: 8px;
    padding: 11px 15px;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    font-weight: bold;
}

button:hover, .botao:hover {
    opacity: .85;
}

.secundario {
    background: var(--painel2);
    color: var(--texto);
}

.perigo {
    background: #b91c1c;
}

.materia {
    background: var(--painel);
    border: 1px solid var(--borda);
    padding: 20px;
    border-radius: 14px;
    margin-bottom: 18px;
}

.materia-topo {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}

.grid-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
    gap: 10px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th, td {
    padding: 12px 8px;
    border-bottom: 1px solid var(--borda);
    text-align: left;
}

th {
    color: var(--suave);
    font-size: 12px;
}

.aviso {
    background: var(--painel2);
    padding: 13px;
    border-radius: 9px;
    margin-bottom: 12px;
}

.status {
    display: inline-block;
    padding: 7px 10px;
    border-radius: 20px;
    background: var(--painel2);
    font-size: 12px;
    font-weight: bold;
}

.aprovado { color: #22c55e; }
.reprovado { color: #f87171; }

details {
    margin-top: 20px;
    cursor: pointer;
}

summary {
    color: var(--azul);
    font-weight: bold;
}

@media(max-width: 650px) {
    header { align-items: flex-start; }
    nav { gap: 12px; }
    h1 { font-size: 24px; }
    .container { padding: 20px 12px; }
    table { font-size: 12px; }
    th, td { padding: 9px 5px; }
}
</style>
</head>

<body class="{{ 'claro' if config.tema == 'claro' else '' }}">

<header>
    <div class="logo">✦ Meu Boletim</div>

    <nav>
        <a href="/">Painel</a>
        <a href="/relatorios">Relatórios</a>
        <a href="/exportar">Exportar</a>
        <a href="/configuracoes">Configurações</a>
    </nav>
</header>

<div class="container">

{% for mensagem in get_flashed_messages() %}
    <div class="aviso">{{ mensagem }}</div>
{% endfor %}

{{ conteudo|safe }}

</div>
</body>
</html>
"""


# ==================================================
# PAINEL
# ==================================================

PAINEL = """
<h1>Olá, {{ config.aluno }} 👋</h1>

<p>
    {% if config.escola %}
        {{ config.escola }} ·
    {% endif %}
    Ano letivo {{ config.ano }}.
    Organize suas notas e acompanhe seu desempenho.
</p>

<div class="cards">

    <div class="card">
        <div class="suave">Pontos conquistados</div>
        <div class="numero">{{ "%.2f"|format(geral.pontos) }}</div>
        <div class="suave">De {{ "%.2f"|format(geral.possivel) }} possíveis</div>
    </div>

    <div class="card">
        <div class="suave">Desempenho do período</div>
        <div class="numero">{{ "%.1f"|format(geral.percentual) }}%</div>
        <div class="barra">
            <div style="width:{{ [geral.percentual,100]|min }}%"></div>
        </div>
    </div>

    <div class="card">
        <div class="suave">Meta anual</div>
        <div class="numero">70%</div>
        <div class="suave">70 pontos de 100</div>
    </div>

    <div class="card">
        <div class="suave">Matérias</div>
        <div class="numero">{{ geral.total }}</div>
        <div class="suave">No seu boletim</div>
    </div>

</div>

<div class="tabs">

    <a href="/?periodo=1"
       class="{{ 'ativo' if periodo == '1' else '' }}">
       1º Trimestre · 30 pts
    </a>

    <a href="/?periodo=2"
       class="{{ 'ativo' if periodo == '2' else '' }}">
       2º Trimestre · 40 pts
    </a>

    <a href="/?periodo=3"
       class="{{ 'ativo' if periodo == '3' else '' }}">
       3º Trimestre · 30 pts
    </a>

    <a href="/?periodo=final"
       class="{{ 'ativo' if periodo == 'final' else '' }}">
       🏆 Resultado final
    </a>

</div>

<div class="box">

    <h2>
        {% if periodo == 'final' %}
            Resultado final do ano
        {% else %}
            Minhas matérias
        {% endif %}
    </h2>

    <form method="GET">
        <input type="hidden" name="periodo" value="{{ periodo }}">

        <input
            name="q"
            value="{{ pesquisa }}"
            placeholder="Pesquisar matéria..."
        >

        <button>Pesquisar</button>
        <a class="botao secundario" href="/?periodo={{ periodo }}">
            Limpar
        </a>
    </form>

</div>


{% if periodo == 'final' %}

<div class="box">

    <h2>🏆 Resumo anual</h2>

    <p>
        O resultado soma os três trimestres:
        30 + 40 + 30 = 100 pontos.
    </p>

    <div class="cards">

        <div class="card">
            <div class="suave">Pontos conquistados</div>
            <div class="numero">
                {{ "%.2f"|format(geral.pontos) }}
            </div>
            <div class="suave">De {{ geral.possivel }} possíveis</div>
        </div>

        <div class="card">
            <div class="suave">Desempenho geral</div>
            <div class="numero">
                {{ "%.1f"|format(geral.percentual) }}%
            </div>
            <div class="barra">
                <div style="width:{{ [geral.percentual,100]|min }}%"></div>
            </div>
        </div>

        <div class="card">
            <div class="suave">Matérias aprovadas</div>
            <div class="numero aprovado">{{ geral.aprovadas }}</div>
        </div>

        <div class="card">
            <div class="suave">Abaixo da média</div>
            <div class="numero reprovado">{{ geral.abaixo_media }}</div>
        </div>

    </div>

    <p>
        A aprovação é calculada individualmente em cada matéria.
        É necessário atingir 70 pontos de 100.
    </p>

</div>

{% for item in dados %}

<div class="materia">

    <div class="materia-topo">
        <h2>{{ item.materia.nome }}</h2>

        <span class="status
            {{ 'aprovado' if item.situacao == 'Aprovado' else 'reprovado' }}">
            {{ item.situacao }}
        </span>
    </div>

    <div class="numero">
        {{ "%.2f"|format(item.pontos) }} / 100
    </div>

    <div class="barra">
        <div style="width:{{ [item.percentual,100]|min }}%"></div>
    </div>

    <p>
        Média final: {{ "%.1f"|format(item.percentual) }}%
    </p>

    <table>
        <tr>
            <th>Trimestre</th>
            <th>Pontos obtidos</th>
            <th>Valor máximo</th>
        </tr>

        {% for t in [1,2,3] %}
        <tr>
            <td>{{ t }}º trimestre</td>
            <td>{{ "%.2f"|format(item.trimestres[t].pontos) }}</td>
            <td>{{ item.trimestres[t].limite }}</td>
        </tr>
        {% endfor %}

        <tr>
            <th>Total anual</th>
            <th>{{ "%.2f"|format(item.pontos) }}</th>
            <th>100</th>
        </tr>
    </table>

    {% if item.situacao != 'Aprovado' %}
        <p>
            Faltam {{ "%.2f"|format(item.faltam) }}
            pontos para atingir a média de aprovação.
        </p>
    {% endif %}

</div>

{% endfor %}

{% else %}

{% for item in dados %}

<div class="materia">

    <div class="materia-topo">

        <div>
            <h2 style="margin-bottom:5px">{{ item.materia.nome }}</h2>

            <p>{{ item.materia.professor or 'Professor não informado' }}</p>
        </div>

        <span class="status">
            {{ item.limite }} pontos disponíveis
        </span>

    </div>

    <div class="cards">

        <div>
            <div class="suave">Pontos obtidos</div>
            <div class="numero">{{ "%.2f"|format(item.pontos) }}</div>
        </div>

        <div>
            <div class="suave">Pontos cadastrados</div>
            <div class="numero">{{ "%.2f"|format(item.valor_cadastrado) }}</div>
        </div>

        <div>
            <div class="suave">Ainda disponíveis</div>
            <div class="numero">{{ "%.2f"|format(item.restante) }}</div>
        </div>

    </div>

    <div class="barra">
        <div style="width:{{ [item.pontos / item.limite * 100,100]|min }}%"></div>
    </div>

    <p>
        {{ "%.1f"|format(item.pontos / item.limite * 100) }}%
        dos pontos do trimestre conquistados.
    </p>

    <h3>Avaliações cadastradas</h3>

    {% if item.avaliacoes %}

    <table>
        <tr>
            <th>Avaliação</th>
            <th>Nota</th>
            <th>Valor</th>
            <th>Data</th>
            <th>Ação</th>
        </tr>

        {% for a in item.avaliacoes %}

        <tr>
            <td>{{ a.nome }}</td>
            <td>{{ "%.2f"|format(a.nota) }}</td>
            <td>{{ "%.2f"|format(a.valor) }}</td>
            <td>{{ a.data or '-' }}</td>
            <td>
                <form method="POST"
                      action="/avaliacao/{{ a.id }}/excluir"
                      onsubmit="return confirm('Excluir esta avaliação?')">

                    <button class="perigo">Excluir</button>

                </form>
            </td>
        </tr>

        {% endfor %}

    </table>

    {% else %}

    <p>Nenhuma avaliação cadastrada neste trimestre.</p>

    {% endif %}

    <h3>Adicionar avaliação</h3>

    <form method="POST" action="/avaliacao/adicionar">

        <input type="hidden" name="materia_id"
               value="{{ item.materia.id }}">

        <input type="hidden" name="trimestre"
               value="{{ periodo }}">

        <div class="grid-form">

            <div>
                <label>Nome da avaliação</label>
                <input name="nome"
                       placeholder="Ex.: Prova objetiva"
                       required>
            </div>

            <div>
                <label>Nota obtida</label>
                <input name="nota" type="number"
                       min="0" step="0.01" required>
            </div>

            <div>
                <label>Valor máximo</label>
                <input name="valor" type="number"
                       min="0.01" step="0.01" required>
            </div>

            <div>
                <label>Data</label>
                <input name="data" type="date">
            </div>

        </div>

        <button>Adicionar avaliação</button>

    </form>

    <details>

        <summary>Editar matéria</summary>

        <form method="POST"
              action="/materia/{{ item.materia.id }}/editar">

            <label>Nome</label>
            <input name="nome"
                   value="{{ item.materia.nome }}"
                   required>

            <label>Professor</label>
            <input name="professor"
                   value="{{ item.materia.professor }}">

            <label>Cor</label>
            <input name="cor" type="color"
                   value="{{ item.materia.cor }}">

            <button>Salvar alterações</button>

        </form>

        <form method="POST"
              action="/materia/{{ item.materia.id }}/excluir"
              onsubmit="return confirm('Excluir matéria e todas as avaliações?')">

            <button class="perigo">Excluir matéria</button>

        </form>

    </details>

</div>

{% endfor %}

{% endif %}


<div class="box">

    <h2>Adicionar nova matéria</h2>

    <form method="POST" action="/materia/adicionar">

        <div class="grid-form">

            <div>
                <label>Nome da matéria</label>
                <input name="nome"
                       placeholder="Ex.: Artes"
                       required>
            </div>

            <div>
                <label>Professor</label>
                <input name="professor"
                       placeholder="Nome do professor">
            </div>

            <div>
                <label>Cor da matéria</label>
                <input name="cor" type="color" value="#3b82f6">
            </div>

        </div>

        <button>Adicionar matéria</button>

    </form>

</div>
"""


# ==================================================
# CONFIGURAÇÕES VISUAIS
# ==================================================

CONFIGURACOES = """
<h1>Configurações</h1>

<p>Personalize seu boletim escolar.</p>

<div class="box">

    <form method="POST">

        <label>Nome do aluno</label>
        <input name="aluno" value="{{ config.aluno }}" required>

        <label>Nome da escola</label>
        <input name="escola" value="{{ config.escola }}">

        <label>Ano letivo</label>
        <input name="ano" type="number" value="{{ config.ano }}" required>

        <label>Tema do site</label>

        <select name="tema">

            <option value="escuro"
                {{ 'selected' if config.tema == 'escuro' else '' }}>
                Escuro
            </option>

            <option value="claro"
                {{ 'selected' if config.tema == 'claro' else '' }}>
                Claro
            </option>

        </select>

        <button>Salvar configurações</button>

    </form>

</div>

<div class="box">

    <h2>Distribuição dos pontos</h2>

    <table>
        <tr>
            <th>Período</th>
            <th>Pontos</th>
        </tr>

        <tr><td>1º trimestre</td><td>30</td></tr>
        <tr><td>2º trimestre</td><td>40</td></tr>
        <tr><td>3º trimestre</td><td>30</td></tr>
        <tr><th>Total anual</th><th>100</th></tr>
    </table>

    <p><strong>Média para aprovação: 70 pontos (70%).</strong></p>

</div>
"""


# ==================================================
# RELATÓRIO
# ==================================================

RELATORIO = """
<h1>Relatório anual</h1>

<p>Comparativo de todas as matérias durante o ano letivo.</p>

<div class="box">

<table>

    <tr>
        <th>Matéria</th>
        <th>1º tri.</th>
        <th>2º tri.</th>
        <th>3º tri.</th>
        <th>Total</th>
        <th>Média</th>
        <th>Situação</th>
    </tr>

    {% for linha in linhas %}

    <tr>

        <td>{{ linha.nome }}</td>

        {% for t in [1,2,3] %}

        <td>
            {{ "%.1f"|format(linha.final.trimestres[t].pontos) }}
        </td>

        {% endfor %}

        <td>
            {{ "%.1f"|format(linha.final.pontos) }}/100
        </td>

        <td>
            {{ "%.1f"|format(linha.final.percentual) }}%
        </td>

        <td class="{{ 'aprovado' if linha.final.situacao == 'Aprovado' else 'reprovado' }}">
            {{ linha.final.situacao }}
        </td>

    </tr>

    {% endfor %}

</table>

</div>

<p>
    A média de aprovação é de {{ media }} pontos.
</p>

<a class="botao" href="/exportar">Exportar notas</a>
"""


# ==================================================
# INICIAR SERVIDOR
# ==================================================

if __name__ == "__main__":
    app.run(debug=False)
