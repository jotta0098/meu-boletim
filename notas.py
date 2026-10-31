
import os
import csv
import io
import sqlite3
from pathlib import Path
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    flash, Response
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "altere-esta-chave")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "boletim.db")))

TRIMESTRES = [1, 2, 3]


# ---------------- BANCO DE DADOS ----------------

def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=20)
    db.row_factory = sqlite3.Row
    return db


def iniciar_banco():
    with conectar() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                aluno TEXT NOT NULL DEFAULT 'Meu Boletim',
                escola TEXT NOT NULL DEFAULT '',
                ano INTEGER NOT NULL DEFAULT 2026,
                media REAL NOT NULL DEFAULT 70,
                escala REAL NOT NULL DEFAULT 100,
                tema TEXT NOT NULL DEFAULT 'escuro'
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
                FOREIGN KEY(materia_id) REFERENCES materias(id)
            )
        """)

        db.execute("""
            INSERT OR IGNORE INTO configuracoes
            (id, aluno, escola, ano, media, escala, tema)
            VALUES (1, 'Meu Boletim', '', 2026, 70, 100, 'escuro')
        """)

        nomes = [
            "Português", "Redação", "Inglês", "Matemática",
            "Física", "Química", "Biologia", "História",
            "Geografia", "Filosofia", "Sociologia"
        ]

        for nome in nomes:
            db.execute(
                "INSERT OR IGNORE INTO materias (nome) VALUES (?)",
                (nome,)
            )


iniciar_banco()


# ---------------- FUNÇÕES ----------------

def configuracoes():
    with conectar() as db:
        return db.execute(
            "SELECT * FROM configuracoes WHERE id = 1"
        ).fetchone()


def obter_materias():
    with conectar() as db:
        return db.execute(
            "SELECT * FROM materias ORDER BY nome"
        ).fetchall()


def calcular_materia(materia_id, trimestre, media_meta):
    with conectar() as db:
        avaliacoes = db.execute("""
            SELECT * FROM avaliacoes
            WHERE materia_id = ? AND trimestre = ?
            ORDER BY id
        """, (materia_id, trimestre)).fetchall()

    pontos = sum(a["nota"] for a in avaliacoes)
    possivel = sum(a["valor"] for a in avaliacoes)
    faltam = max(0, media_meta - pontos)

    percentual = (pontos / possivel * 100) if possivel > 0 else 0

    if pontos >= media_meta:
        status = "Aprovado"
    elif possivel >= media_meta and pontos < media_meta:
        status = "Em andamento"
    else:
        status = "Atenção"

    return {
        "avaliacoes": avaliacoes,
        "pontos": pontos,
        "possivel": possivel,
        "percentual": percentual,
        "faltam": faltam,
        "status": status
    }


def layout(conteudo, titulo="Meu Boletim"):
    config = configuracoes()
    return render_template_string(
        TEMPLATE,
        conteudo=conteudo,
        titulo=titulo,
        config=config
    )


# ---------------- PAINEL ----------------

@app.route("/")
def inicio():
    config = configuracoes()
    trimestre = request.args.get("trimestre", 1, type=int)

    if trimestre not in TRIMESTRES:
        trimestre = 1

    pesquisa = request.args.get("q", "").strip()
    materias = obter_materias()

    dados = []
    soma_pontos = 0
    soma_possivel = 0
    aprovadas = 0
    atencao = 0

    for materia in materias:
        if pesquisa and pesquisa.lower() not in materia["nome"].lower():
            continue

        resultado = calcular_materia(
            materia["id"], trimestre, config["media"]
        )

        if resultado["possivel"] > 0:
            soma_pontos += resultado["pontos"]
            soma_possivel += resultado["possivel"]

        if resultado["status"] == "Aprovado":
            aprovadas += 1
        elif resultado["status"] == "Atenção":
            atencao += 1

        dados.append({
            "materia": materia,
            **resultado
        })

    percentual_geral = (
        soma_pontos / soma_possivel * 100
        if soma_possivel else 0
    )

    geral = {
        "pontos": soma_pontos,
        "possivel": soma_possivel,
        "percentual": percentual_geral,
        "aprovadas": aprovadas,
        "atencao": atencao,
        "total": len(materias)
    }

    return layout(
        render_template_string(
            PAINEL,
            dados=dados,
            geral=geral,
            trimestre=trimestre,
            pesquisa=pesquisa
        ),
        "Painel | Meu Boletim"
    )


# ---------------- ADICIONAR MATÉRIA ----------------

@app.route("/materia/adicionar", methods=["POST"])
def adicionar_materia():
    nome = request.form.get("nome", "").strip()
    professor = request.form.get("professor", "").strip()
    cor = request.form.get("cor", "#3b82f6")

    if not nome:
        flash("Digite o nome da matéria.")
        return redirect(url_for("inicio"))

    try:
        with conectar() as db:
            db.execute("""
                INSERT INTO materias (nome, professor, cor)
                VALUES (?, ?, ?)
            """, (nome, professor, cor))

        flash("Matéria adicionada com sucesso!")

    except sqlite3.IntegrityError:
        flash("Essa matéria já existe.")

    return redirect(url_for("inicio"))


# ---------------- EDITAR MATÉRIA ----------------

@app.route("/materia/<int:materia_id>/editar", methods=["POST"])
def editar_materia(materia_id):
    nome = request.form.get("nome", "").strip()
    professor = request.form.get("professor", "").strip()
    cor = request.form.get("cor", "#3b82f6")

    if not nome:
        flash("O nome da matéria não pode ficar vazio.")
        return redirect(url_for("inicio"))

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

    return redirect(url_for("inicio"))


# ---------------- EXCLUIR MATÉRIA ----------------

@app.route("/materia/<int:materia_id>/excluir", methods=["POST"])
def excluir_materia(materia_id):
    with conectar() as db:
        db.execute(
            "DELETE FROM avaliacoes WHERE materia_id = ?",
            (materia_id,)
        )
        db.execute(
            "DELETE FROM materias WHERE id = ?",
            (materia_id,)
        )

    flash("Matéria e avaliações excluídas.")
    return redirect(url_for("inicio"))


# ---------------- ADICIONAR AVALIAÇÃO ----------------

@app.route("/avaliacao/adicionar", methods=["POST"])
def adicionar_avaliacao():
    try:
        materia_id = int(request.form["materia_id"])
        trimestre = int(request.form["trimestre"])
        nome = request.form.get("nome", "").strip()
        nota = float(request.form["nota"].replace(",", "."))
        valor = float(request.form["valor"].replace(",", "."))
        data = request.form.get("data", "")

        if trimestre not in TRIMESTRES:
            raise ValueError()

        if not nome or valor <= 0 or nota < 0 or nota > valor:
            flash("Confira o nome, a nota e o valor da avaliação.")
            return redirect(url_for("inicio", trimestre=trimestre))

        with conectar() as db:
            materia = db.execute(
                "SELECT id FROM materias WHERE id = ?",
                (materia_id,)
            ).fetchone()

            if not materia:
                flash("Matéria não encontrada.")
                return redirect(url_for("inicio"))

            db.execute("""
                INSERT INTO avaliacoes
                (materia_id, trimestre, nome, nota, valor, data)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (materia_id, trimestre, nome, nota, valor, data))

        flash("Avaliação cadastrada!")

    except (ValueError, KeyError):
        flash("Dados inválidos. Confira os campos.")

    except Exception:
        app.logger.exception("Erro ao adicionar avaliação")
        flash("Não foi possível salvar a avaliação.")

    return redirect(url_for("inicio", trimestre=request.form.get("trimestre", 1)))


# ---------------- EDITAR AVALIAÇÃO ----------------

@app.route("/avaliacao/<int:avaliacao_id>/editar", methods=["POST"])
def editar_avaliacao(avaliacao_id):
    try:
        nota = float(request.form["nota"].replace(",", "."))
        valor = float(request.form["valor"].replace(",", "."))
        nome = request.form.get("nome", "").strip()
        data = request.form.get("data", "")

        if not nome or valor <= 0 or nota < 0 or nota > valor:
            flash("Confira os valores da avaliação.")
            return redirect(url_for("inicio"))

        with conectar() as db:
            db.execute("""
                UPDATE avaliacoes
                SET nome = ?, nota = ?, valor = ?, data = ?
                WHERE id = ?
            """, (nome, nota, valor, data, avaliacao_id))

        flash("Avaliação atualizada!")

    except (ValueError, KeyError):
        flash("Dados inválidos.")

    return redirect(url_for("inicio"))


# ---------------- EXCLUIR AVALIAÇÃO ----------------

@app.route("/avaliacao/<int:avaliacao_id>/excluir", methods=["POST"])
def excluir_avaliacao(avaliacao_id):
    with conectar() as db:
        db.execute(
            "DELETE FROM avaliacoes WHERE id = ?",
            (avaliacao_id,)
        )

    flash("Avaliação excluída.")
    return redirect(url_for("inicio"))


# ---------------- CONFIGURAÇÕES ----------------

@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes_pagina():
    if request.method == "POST":
        try:
            aluno = request.form.get("aluno", "").strip()
            escola = request.form.get("escola", "").strip()
            ano = int(request.form.get("ano"))
            media = float(request.form.get("media").replace(",", "."))
            escala = float(request.form.get("escala").replace(",", "."))
            tema = request.form.get("tema", "escuro")

            if not aluno or not 0 < media <= escala or escala <= 0:
                raise ValueError()

            if tema not in ("escuro", "claro"):
                tema = "escuro"

            with conectar() as db:
                db.execute("""
                    UPDATE configuracoes
                    SET aluno = ?, escola = ?, ano = ?,
                        media = ?, escala = ?, tema = ?
                    WHERE id = 1
                """, (aluno, escola, ano, media, escala, tema))

            flash("Configurações salvas!")

        except (ValueError, AttributeError):
            flash("Confira os valores informados.")

        return redirect(url_for("configuracoes_pagina"))

    return layout(
        render_template_string(CONFIG),
        "Configurações | Meu Boletim"
    )


# ---------------- RELATÓRIO ----------------

@app.route("/relatorios")
def relatorios():
    config = configuracoes()
    materias = obter_materias()
    linhas = []

    for materia in materias:
        trimestres = []

        for t in TRIMESTRES:
            resultado = calcular_materia(
                materia["id"], t, config["media"]
            )
            trimestres.append(resultado)

        linhas.append({
            "nome": materia["nome"],
            "trimestres": trimestres
        })

    return layout(
        render_template_string(REPORT, linhas=linhas),
        "Relatórios | Meu Boletim"
    )


# ---------------- EXPORTAR CSV ----------------

@app.route("/exportar")
def exportar():
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")

    escritor.writerow([
        "Matéria", "Trimestre", "Avaliação",
        "Nota obtida", "Valor máximo", "Data"
    ])

    with conectar() as db:
        registros = db.execute("""
            SELECT m.nome AS materia, a.trimestre,
                   a.nome AS avaliacao, a.nota,
                   a.valor, a.data
            FROM avaliacoes a
            JOIN materias m ON m.id = a.materia_id
            ORDER BY m.nome, a.trimestre, a.id
        """).fetchall()

    for r in registros:
        escritor.writerow([
            r["materia"], r["trimestre"], r["avaliacao"],
            r["nota"], r["valor"], r["data"]
        ])

    return Response(
        "\ufeff" + saida.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=meu_boletim.csv"
        }
    )


# ---------------- SAÚDE DO SERVIDOR ----------------

@app.route("/health")
def health():
    try:
        with conectar() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "banco": "conectado"}
    except Exception:
        app.logger.exception("Erro no banco")
        return {"status": "erro"}, 500


# ---------------- INTERFACE ----------------

TEMPLATE = """
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
    font-family: Inter, Arial, sans-serif;
}
header {
    background: var(--painel);
    border-bottom: 1px solid var(--borda);
    padding: 18px 5%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
}
.logo { font-size: 22px; font-weight: 800; color: var(--azul); }
nav { display: flex; gap: 18px; flex-wrap: wrap; }
nav a { color: var(--suave); text-decoration: none; font-size: 14px; }
nav a:hover { color: var(--azul); }
.container { max-width: 1250px; margin: auto; padding: 30px 18px; }
h1 { font-size: 30px; margin-bottom: 8px; }
h2 { font-size: 20px; }
p { color: var(--suave); }
.cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 15px;
    margin: 25px 0;
}
.card, .box {
    background: var(--painel);
    border: 1px solid var(--borda);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 17px;
}
.numero { font-size: 30px; font-weight: 800; margin: 10px 0; }
.suave { color: var(--suave); font-size: 13px; }
.barra { background: var(--painel2); height: 9px; border-radius: 20px; overflow: hidden; }
.barra div { height: 100%; background: var(--azul); border-radius: 20px; }
.tabs { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
.tabs a {
    padding: 12px 17px; border-radius: 9px;
    background: var(--painel2); color: var(--texto);
    text-decoration: none;
}
.tabs a.ativo { background: var(--azul); color: white; }
input, select {
    padding: 12px; border-radius: 8px;
    border: 1px solid var(--borda);
    background: var(--painel2); color: var(--texto);
    width: 100%; margin: 5px 0 12px;
}
button, .botao {
    border: 0; background: var(--azul); color: white;
    border-radius: 8px; padding: 11px 15px;
    cursor: pointer; text-decoration: none; display: inline-block;
    font-weight: 700;
}
button:hover, .botao:hover { opacity: .85; }
.perigo { background: #b91c1c; }
.secundario { background: var(--painel2); color: var(--texto); }
.grid-form {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
    gap: 10px;
}
.materia {
    background: var(--painel); border: 1px solid var(--borda);
    padding: 20px; border-radius: 14px; margin-bottom: 18px;
}
.materia-topo {
    display: flex; justify-content: space-between;
    gap: 10px; align-items: center; flex-wrap: wrap;
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 8px; border-bottom: 1px solid var(--borda); text-align: left; }
th { color: var(--suave); font-size: 12px; }
.aviso { background: var(--painel2); padding: 12px; border-radius: 9px; margin-bottom: 12px; }
.status { font-size: 12px; padding: 6px 9px; border-radius: 20px; background: var(--painel2); }
form.inline { display: inline; }
@media(max-width:650px) {
    header { align-items: flex-start; }
    nav { gap: 12px; }
    h1 { font-size: 25px; }
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
        <a href="/exportar">Exportar notas</a>
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


PAINEL = """
<h1>Olá, {{ config.aluno }} 👋</h1>
<p>Acompanhe sua vida escolar e veja como está seu desempenho.</p>

<div class="cards">
    <div class="card">
        <div class="suave">Pontos conquistados</div>
        <div class="numero">{{ "%.1f"|format(geral.pontos) }}</div>
        <div class="suave">De {{ "%.1f"|format(geral.possivel) }} possíveis</div>
    </div>
    <div class="card">
        <div class="suave">Desempenho geral</div>
        <div class="numero">{{ "%.1f"|format(geral.percentual) }}%</div>
        <div class="barra"><div style="width:{{ [geral.percentual, 100]|min }}%"></div></div>
    </div>
    <div class="card">
        <div class="suave">Meta de aprovação</div>
        <div class="numero">{{ config.media }}</div>
        <div class="suave">Pontos necessários</div>
    </div>
    <div class="card">
        <div class="suave">Matérias cadastradas</div>
        <div class="numero">{{ geral.total }}</div>
        <div class="suave">No seu boletim</div>
    </div>
</div>

<div class="tabs">
    {% for t in [1,2,3] %}
        <a class="{{ 'ativo' if trimestre == t else '' }}"
           href="/?trimestre={{ t }}">{{ t }}º Trimestre</a>
    {% endfor %}
</div>

<div class="box">
    <h2>Minhas matérias</h2>
    <form method="GET">
        <input type="hidden" name="trimestre" value="{{ trimestre }}">
        <input name="q" value="{{ pesquisa }}" placeholder="Pesquisar matéria...">
        <button>Pesquisar</button>
        <a class="botao secundario" href="/?trimestre={{ trimestre }}">Limpar</a>
    </form>
</div>

{% for item in dados %}
<div class="materia">
    <div class="materia-topo">
        <div>
            <h2 style="margin:0">{{ item.materia.nome }}</h2>
            <p>{{ item.materia.professor or 'Professor não informado' }}</p>
        </div>
        <span class="status">{{ item.status }}</span>
    </div>

    <div class="cards">
        <div>
            <div class="suave">Pontos obtidos</div>
            <strong class="numero">{{ "%.1f"|format(item.pontos) }}</strong>
        </div>
        <div>
            <div class="suave">Valor total</div>
            <strong class="numero">{{ "%.1f"|format(item.possivel) }}</strong>
        </div>
        <div>
            <div class="suave">Faltam para a meta</div>
            <strong class="numero">{{ "%.1f"|format(item.faltam) }}</strong>
        </div>
    </div>

    <div class="barra">
        <div style="width:{{ [item.percentual, 100]|min }}%"></div>
    </div>
    <p>{{ "%.1f"|format(item.percentual) }}% do total possível registrado</p>

    <h3>Avaliações cadastradas</h3>
    {% if item.avaliacoes %}
    <table>
        <tr><th>Avaliação</th><th>Nota</th><th>Valor</th><th>Data</th><th>Ação</th></tr>
        {% for a in item.avaliacoes %}
        <tr>
            <td>{{ a.nome }}</td>
            <td>{{ a.nota }}</td>
            <td>{{ a.valor }}</td>
            <td>{{ a.data or '-' }}</td>
            <td>
                <form class="inline" method="POST" action="/avaliacao/{{ a.id }}/excluir"
                onsubmit="return confirm('Excluir avaliação?')">
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
        <input type="hidden" name="materia_id" value="{{ item.materia.id }}">
        <input type="hidden" name="trimestre" value="{{ trimestre }}">
        <div class="grid-form">
            <div><label>Nome</label><input name="nome" placeholder="Ex.: Prova objetiva" required></div>
            <div><label>Nota obtida</label><input name="nota" type="number" min="0" step="0.01" required></div>
            <div><label>Valor máximo</label><input name="valor" type="number" min="0.01" step="0.01" required></div>
            <div><label>Data</label><input name="data" type="date"></div>
        </div>
        <button>Adicionar avaliação</button>
    </form>

    <details style="margin-top:20px">
        <summary>Editar matéria</summary>
        <form method="POST" action="/materia/{{ item.materia.id }}/editar">
            <input name="nome" value="{{ item.materia.nome }}" required>
            <input name="professor" value="{{ item.materia.professor }}" placeholder="Professor">
            <label>Cor da matéria</label>
            <input name="cor" type="color" value="{{ item.materia.cor }}">
            <button>Salvar alterações</button>
        </form>
        <form method="POST" action="/materia/{{ item.materia.id }}/excluir"
        onsubmit="return confirm('Excluir matéria e todas as suas avaliações?')">
            <button class="perigo">Excluir matéria</button>
        </form>
    </details>
</div>
{% endfor %}

<div class="box">
    <h2>Adicionar matéria</h2>
    <form method="POST" action="/materia/adicionar">
        <div class="grid-form">
            <div><label>Nome</label><input name="nome" placeholder="Ex.: Artes" required></div>
            <div><label>Professor</label><input name="professor" placeholder="Nome do professor"></div>
            <div><label>Cor</label><input name="cor" type="color" value="#3b82f6"></div>
        </div>
        <button>Adicionar matéria</button>
    </form>
</div>
"""


CONFIG = """
<h1>Configurações</h1>
<p>Personalize o sistema de acordo com as regras da sua escola.</p>

<div class="box">
<form method="POST">
    <label>Nome do aluno</label>
    <input name="aluno" value="{{ config.aluno }}" required>

    <label>Nome da escola</label>
    <input name="escola" value="{{ config.escola }}">

    <label>Ano letivo</label>
    <input name="ano" type="number" value="{{ config.ano }}" required>

    <label>Nota mínima para aprovação</label>
    <input name="media" type="number" step="0.01" min="0.01"
    value="{{ config.media }}" required>

    <label>Escala máxima de notas</label>
    <input name="escala" type="number" step="0.01" min="1"
    value="{{ config.escala }}" required>

    <label>Tema do site</label>
    <select name="tema">
        <option value="escuro" {{ 'selected' if config.tema == 'escuro' else '' }}>Escuro</option>
        <option value="claro" {{ 'selected' if config.tema == 'claro' else '' }}>Claro</option>
    </select>

    <button>Salvar configurações</button>
</form>
</div>

<div class="box">
<h2>Como funciona a meta?</h2>
<p>O sistema soma as notas cadastradas em cada matéria e compara o resultado com a meta de aprovação.</p>
<p>Se sua escola exige 70 pontos, configure a meta como 70.</p>
</div>
"""


REPORT = """
<h1>Relatórios escolares</h1>
<p>Compare o desempenho das matérias nos três trimestres.</p>

<div class="box">
<table>
<tr>
    <th>Matéria</th>
    <th>1º trimestre</th>
    <th>2º trimestre</th>
    <th>3º trimestre</th>
</tr>
{% for linha in linhas %}
<tr>
    <td>{{ linha.nome }}</td>
    {% for t in linha.trimestres %}
    <td>
        {{ "%.1f"|format(t.pontos) }} / {{ "%.1f"|format(t.possivel) }}
        <br><span class="suave">{{ "%.1f"|format(t.percentual) }}%</span>
    </td>
    {% endfor %}
</tr>
{% endfor %}
</table>
</div>

<a class="botao" href="/exportar">Baixar relatório CSV</a>
"""


if __name__ == "__main__":
    app.run(debug=False)
