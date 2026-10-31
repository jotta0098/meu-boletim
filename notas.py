
import os
import sqlite3
from pathlib import Path
from flask import Flask, request, redirect, url_for, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "meu-boletim-chave-local")

BASE_DIR = Path(__file__).resolve().parent
BANCO = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "boletim.db")))

MATERIAS_INICIAIS = [
    "Português", "Redação", "Inglês", "Matemática",
    "Física", "Química", "Biologia", "História",
    "Geografia", "Filosofia", "Sociologia"
]

AVALIACOES = [
    "Simulado 1",
    "Simulado 2",
    "Prova Objetiva",
    "Prova Discursiva",
    "Qualitativo",
    "Atividade"
]


def conectar():
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(BANCO), timeout=20)
    db.row_factory = sqlite3.Row
    return db


def criar_banco():
    with conectar() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_id INTEGER NOT NULL,
                trimestre INTEGER NOT NULL,
                avaliacao TEXT NOT NULL,
                nota REAL NOT NULL DEFAULT 0,
                valor REAL NOT NULL DEFAULT 0,
                UNIQUE(materia_id, trimestre, avaliacao),
                FOREIGN KEY(materia_id) REFERENCES materias(id)
            )
        """)

        for nome in MATERIAS_INICIAIS:
            db.execute(
                "INSERT OR IGNORE INTO materias (nome) VALUES (?)",
                (nome,)
            )


criar_banco()


@app.route("/")
def inicio():
    trimestre = request.args.get("trimestre", "1")

    try:
        trimestre = int(trimestre)
        if trimestre not in (1, 2, 3):
            trimestre = 1
    except ValueError:
        trimestre = 1

    with conectar() as db:
        materias = db.execute(
            "SELECT * FROM materias ORDER BY nome"
        ).fetchall()

        dados = []

        for materia in materias:
            avaliacoes = []
            total_nota = 0
            total_valor = 0

            for indice, avaliacao in enumerate(AVALIACOES):
                registro = db.execute("""
                    SELECT nota, valor FROM notas
                    WHERE materia_id = ?
                    AND trimestre = ?
                    AND avaliacao = ?
                """, (materia["id"], trimestre, avaliacao)).fetchone()

                nota = registro["nota"] if registro else 0
                valor = registro["valor"] if registro else 0

                total_nota += nota
                total_valor += valor

                avaliacoes.append({
                    "nome": avaliacao,
                    "indice": indice,
                    "nota": nota,
                    "valor": valor
                })

            porcentagem = (
                (total_nota / total_valor) * 100
                if total_valor > 0 else 0
            )

            # NOVO: soma as notas e os valores dos três trimestres
            anual = db.execute("""
                SELECT
                    COALESCE(SUM(nota), 0) AS total_nota,
                    COALESCE(SUM(valor), 0) AS total_valor
                FROM notas
                WHERE materia_id = ?
                AND trimestre IN (1, 2, 3)
            """, (materia["id"],)).fetchone()

            dados.append({
                "id": materia["id"],
                "nome": materia["nome"],
                "avaliacoes": avaliacoes,
                "total_nota": total_nota,
                "total_valor": total_valor,
                "porcentagem": porcentagem,

                # Dados do ano inteiro
                "anual_nota": anual["total_nota"],
                "anual_valor": anual["total_valor"]
            })

    return render_template_string(
        HTML,
        materias=dados,
        trimestre=trimestre
    )


@app.route("/salvar", methods=["POST"])
def salvar():
    try:
        materia_id = int(request.form.get("materia_id"))
        trimestre = int(request.form.get("trimestre"))

        if trimestre not in (1, 2, 3):
            raise ValueError("Trimestre inválido.")

        with conectar() as db:
            existe = db.execute(
                "SELECT id FROM materias WHERE id = ?",
                (materia_id,)
            ).fetchone()

            if not existe:
                flash("Matéria não encontrada.")
                return redirect(url_for("inicio", trimestre=trimestre))

            for indice, avaliacao in enumerate(AVALIACOES):
                nota_texto = request.form.get(
                    f"nota_{indice}", ""
                ).strip()

                valor_texto = request.form.get(
                    f"valor_{indice}", ""
                ).strip()

                nota = (
                    float(nota_texto.replace(",", "."))
                    if nota_texto else 0
                )

                valor = (
                    float(valor_texto.replace(",", "."))
                    if valor_texto else 0
                )

                if nota < 0 or valor < 0 or nota > valor:
                    flash(
                        f"Confira os valores de {avaliacao}. "
                        "A nota não pode ser maior que o valor da avaliação."
                    )
                    return redirect(
                        url_for("inicio", trimestre=trimestre)
                    )

                db.execute("""
                    INSERT INTO notas
                    (materia_id, trimestre, avaliacao, nota, valor)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(materia_id, trimestre, avaliacao)
                    DO UPDATE SET
                        nota = excluded.nota,
                        valor = excluded.valor
                """, (materia_id, trimestre, avaliacao, nota, valor))

        flash("Notas salvas com sucesso!")

    except (ValueError, TypeError):
        flash("Confira os números digitados.")

    except Exception:
        app.logger.exception("Erro ao salvar notas")
        flash("Ocorreu um erro ao salvar as notas.")

    return redirect(url_for("inicio", trimestre=trimestre))


@app.route("/adicionar-materia", methods=["POST"])
def adicionar_materia():
    nome = request.form.get("nome", "").strip()

    if not nome:
        flash("Digite o nome da matéria.")
        return redirect(url_for("inicio"))

    try:
        with conectar() as db:
            db.execute(
                "INSERT INTO materias (nome) VALUES (?)",
                (nome,)
            )

        flash("Matéria adicionada com sucesso!")

    except sqlite3.IntegrityError:
        flash("Essa matéria já existe.")

    except Exception:
        app.logger.exception("Erro ao adicionar matéria")
        flash("Não foi possível adicionar a matéria.")

    return redirect(url_for("inicio"))


@app.route("/excluir-materia/<int:materia_id>", methods=["POST"])
def excluir_materia(materia_id):
    with conectar() as db:
        db.execute(
            "DELETE FROM notas WHERE materia_id = ?",
            (materia_id,)
        )

        db.execute(
            "DELETE FROM materias WHERE id = ?",
            (materia_id,)
        )

    flash("Matéria excluída.")
    return redirect(url_for("inicio"))


@app.route("/health")
def health():
    try:
        with conectar() as db:
            db.execute("SELECT 1")

        return {"status": "ok", "banco": "conectado"}

    except Exception:
        app.logger.exception("Erro no banco")
        return {"status": "erro"}, 500


HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meu Boletim</title>

<style>
* { box-sizing: border-box; }

body {
    margin: 0;
    background: #0f172a;
    color: white;
    font-family: Arial, sans-serif;
}

header {
    background: #1e293b;
    padding: 25px 15px;
    text-align: center;
}

header h1 {
    color: #60a5fa;
    margin: 0;
}

header p { color: #cbd5e1; }

.container {
    max-width: 1100px;
    margin: 25px auto;
    padding: 15px;
}

.trimestres {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}

.trimestres a {
    flex: 1;
    text-align: center;
    padding: 14px 5px;
    background: #334155;
    color: white;
    text-decoration: none;
    border-radius: 8px;
}

.trimestres a.ativo {
    background: #2563eb;
}

.card {
    background: #1e293b;
    padding: 20px;
    margin-bottom: 20px;
    border-radius: 12px;
}

h2 { color: #60a5fa; }

.grade {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
}

.grade th, .grade td {
    padding: 10px 5px;
    border-bottom: 1px solid #475569;
    text-align: left;
}

.grade input {
    width: 75px;
    padding: 9px;
    border-radius: 6px;
    border: none;
    background: #f1f5f9;
}

button {
    background: #2563eb;
    color: white;
    border: none;
    padding: 12px 18px;
    border-radius: 7px;
    cursor: pointer;
    font-weight: bold;
}

button:hover { background: #1d4ed8; }

.total {
    background: #334155;
    padding: 15px;
    border-radius: 8px;
    margin: 12px 0;
    line-height: 1.8;
}

.adicionar {
    display: flex;
    gap: 10px;
}

.adicionar input {
    flex: 1;
    min-width: 0;
    padding: 12px;
    border-radius: 7px;
    border: none;
}

.aviso {
    padding: 12px;
    background: #334155;
    border-radius: 8px;
    margin-bottom: 15px;
}

.excluir { background: #991b1b; }

.total-anual {
    background: #172554;
    border: 1px solid #2563eb;
    padding: 15px;
    border-radius: 8px;
    margin-top: 12px;
    line-height: 1.9;
}

.total-anual strong {
    color: #93c5fd;
}

.pontos-anual {
    color: #4ade80;
    font-size: 20px;
    font-weight: bold;
}

@media(max-width: 650px) {
    .grade { font-size: 12px; }
    .grade input { width: 55px; padding: 7px 3px; }
    .grade th, .grade td { padding: 8px 3px; }
}
</style>
</head>

<body>

<header>
    <h1>Meu Boletim</h1>
    <p>Organize suas notas e acompanhe seu desempenho escolar.</p>
</header>

<div class="container">

{% for mensagem in get_flashed_messages() %}
    <div class="aviso">{{ mensagem }}</div>
{% endfor %}

<h2>Selecione o trimestre</h2>

<div class="trimestres">
    <a href="/?trimestre=1"
    class="{{ 'ativo' if trimestre == 1 else '' }}">
        1º Trimestre
    </a>

    <a href="/?trimestre=2"
    class="{{ 'ativo' if trimestre == 2 else '' }}">
        2º Trimestre
    </a>

    <a href="/?trimestre=3"
    class="{{ 'ativo' if trimestre == 3 else '' }}">
        3º Trimestre
    </a>
</div>

{% for materia in materias %}
<div class="card">

    <h2>{{ materia.nome }}</h2>

    <form method="POST" action="/salvar">
        <input type="hidden" name="materia_id"
        value="{{ materia.id }}">

        <input type="hidden" name="trimestre"
        value="{{ trimestre }}">

        <div style="overflow-x:auto">
        <table class="grade">
            <thead>
                <tr>
                    <th>Avaliação</th>
                    <th>Nota</th>
                    <th>Vale</th>
                </tr>
            </thead>

            <tbody>
            {% for avaliacao in materia.avaliacoes %}
                <tr>
                    <td>{{ avaliacao.nome }}</td>

                    <td>
                        <input type="number"
                        name="nota_{{ avaliacao.indice }}"
                        min="0" step="0.01" max="100"
                        value="{{ avaliacao.nota if avaliacao.nota else '' }}"
                        placeholder="0">
                    </td>

                    <td>
                        <input type="number"
                        name="valor_{{ avaliacao.indice }}"
                        min="0" step="0.01" max="100"
                        value="{{ avaliacao.valor if avaliacao.valor else '' }}"
                        placeholder="0">
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        </div>

        <button type="submit">Salvar notas</button>
    </form>

    <div class="total">
        <strong>Total obtido neste trimestre:</strong>
        {{ "%.2f"|format(materia.total_nota) }} pontos<br>

        <strong>Total possível neste trimestre:</strong>
        {{ "%.2f"|format(materia.total_valor) }} pontos<br>

        <strong>Porcentagem:</strong>
        {{ "%.1f"|format(materia.porcentagem) }}%
    </div>

    <form method="POST"
    action="/excluir-materia/{{ materia.id }}"
    onsubmit="return confirm('Deseja excluir esta matéria e suas notas?')">

        <button class="excluir" type="submit">
            Excluir matéria
        </button>
    </form>

</div>
{% endfor %}


<!-- NOVA SEÇÃO: TOTAL DOS TRÊS TRIMESTRES -->

<div class="card">
    <h2>🏆 Total dos três trimestres</h2>

    <p style="color:#cbd5e1">
        Aqui aparece a soma de tudo que você conseguiu durante o ano
        e o valor total das avaliações cadastradas.
    </p>

    <div style="overflow-x:auto">
    <table class="grade">
        <thead>
            <tr>
                <th>Matéria</th>
                <th>Pontos conseguidos</th>
                <th>Valor total</th>
                <th>Porcentagem</th>
            </tr>
        </thead>

        <tbody>
        {% for materia in materias %}
            <tr>
                <td>
                    <strong>{{ materia.nome }}</strong>
                </td>

                <td>
                    <span class="pontos-anual">
                        {{ "%.2f"|format(materia.anual_nota) }}
                    </span>
                </td>

                <td>
                    {{ "%.2f"|format(materia.anual_valor) }}
                </td>

                <td>
                    {{ "%.1f"|format(
                        (materia.anual_nota / materia.anual_valor * 100)
                        if materia.anual_valor > 0 else 0
                    ) }}%
                </td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    </div>

    <p style="color:#cbd5e1;font-size:13px">
        O total é atualizado automaticamente sempre que você salva
        as notas de qualquer trimestre.
    </p>
</div>


<div class="card">
    <h2>Adicionar nova matéria</h2>

    <form method="POST" action="/adicionar-materia"
    class="adicionar">

        <input type="text" name="nome"
        placeholder="Nome da matéria" required>

        <button type="submit">Adicionar</button>
    </form>
</div>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(debug=False)
