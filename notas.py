
import os
import sqlite3
import logging
from pathlib import Path
from functools import wraps

from flask import (
    Flask, request, redirect, session,
    flash, render_template_string, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape

# CONFIGURAÇÃO
app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-troque-no-render"
)

BASE_DIR = Path(__file__).resolve().parent
BANCO = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "boletim.db")))

logging.basicConfig(level=logging.INFO)


# BANCO DE DADOS
def conectar():
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(str(BANCO), timeout=20)
    conexao.row_factory = sqlite3.Row
    return conexao


def criar_banco():
    with conectar() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                trimestre INTEGER NOT NULL,
                nota REAL NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        """)


# Inicializa o banco quando o Gunicorn importa o aplicativo.
criar_banco()


@app.before_request
def garantir_banco():
    # Também verifica a existência das tabelas antes de cada requisição.
    criar_banco()


# FUNÇÕES AUXILIARES
def usuario_atual():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    with conectar() as db:
        return db.execute(
            "SELECT id, email FROM usuarios WHERE id = ?",
            (usuario_id,)
        ).fetchone()


def proteger(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Faça login para acessar o sistema.")
            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar


def pagina(titulo, conteudo):
    usuario = usuario_atual()

    menu = ""

    if usuario:
        menu = """
        <nav>
            <a href="/boletim">Meu boletim</a>
            <a href="/sair">Sair</a>
        </nav>
        """

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{{ titulo }}</title>
        <style>
            * { box-sizing: border-box; }

            body {
                margin: 0;
                padding: 20px;
                background: #101827;
                color: white;
                font-family: Arial, sans-serif;
            }

            main {
                max-width: 850px;
                margin: 35px auto;
                background: #1e293b;
                padding: 25px;
                border-radius: 15px;
            }

            h1, h2 { color: #60a5fa; }

            input, select, button {
                width: 100%;
                padding: 13px;
                margin: 8px 0;
                border: none;
                border-radius: 8px;
                font-size: 16px;
            }

            button {
                background: #2563eb;
                color: white;
                cursor: pointer;
                font-weight: bold;
            }

            button:hover { background: #1d4ed8; }

            a { color: #93c5fd; }

            nav {
                display: flex;
                justify-content: space-between;
                margin-bottom: 25px;
            }

            .aviso {
                background: #334155;
                padding: 12px;
                border-radius: 8px;
                margin: 10px 0;
            }

            .materia {
                background: #334155;
                padding: 15px;
                margin: 10px 0;
                border-radius: 8px;
            }

            .pequeno { color: #cbd5e1; font-size: 14px; }
        </style>
    </head>
    <body>
        <main>
            {{ menu|safe }}

            {% for mensagem in get_flashed_messages() %}
                <div class="aviso">{{ mensagem }}</div>
            {% endfor %}

            {{ conteudo|safe }}
        </main>
    </body>
    </html>
    """, titulo=titulo, conteudo=conteudo, menu=menu)


# PÁGINA INICIAL
@app.route("/")
def inicio():
    if session.get("usuario_id"):
        return redirect(url_for("boletim"))

    return redirect(url_for("login"))


# CRIAR CONTA
@app.route("/criar-conta", methods=["GET", "POST"])
def criar_conta():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Preencha todos os campos.")
            return redirect(url_for("criar_conta"))

        if len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.")
            return redirect(url_for("criar_conta"))

        senha_hash = generate_password_hash(senha)

        try:
            with conectar() as db:
                cursor = db.execute(
                    "INSERT INTO usuarios (email, senha) VALUES (?, ?)",
                    (email, senha_hash)
                )
                usuario_id = cursor.lastrowid

            session.clear()
            session["usuario_id"] = usuario_id

            return redirect(url_for("boletim"))

        except sqlite3.IntegrityError:
            flash("Esse e-mail já possui uma conta.")
            return redirect(url_for("login"))

        except Exception:
            app.logger.exception("Erro ao criar conta")
            flash("Não foi possível criar sua conta. Tente novamente.")
            return redirect(url_for("criar_conta"))

    conteudo = """
        <h1>Criar conta</h1>
        <p>Crie sua conta gratuitamente para acessar seu boletim.</p>

        <form method="POST">
            <input type="email" name="email"
                placeholder="Seu e-mail" required>

            <input type="password" name="senha"
                placeholder="Crie uma senha" minlength="6" required>

            <button type="submit">Criar minha conta</button>
        </form>

        <p>Já tem uma conta? <a href="/login">Fazer login</a></p>
    """

    return pagina("Criar conta", conteudo)


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario_id"):
        return redirect(url_for("boletim"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Preencha o e-mail e a senha.")
            return redirect(url_for("login"))

        try:
            with conectar() as db:
                usuario = db.execute(
                    "SELECT id, email, senha FROM usuarios WHERE email = ?",
                    (email,)
                ).fetchone()

            if usuario and check_password_hash(usuario["senha"], senha):
                session.clear()
                session["usuario_id"] = usuario["id"]
                return redirect(url_for("boletim"))

            flash("E-mail ou senha incorretos.")
            return redirect(url_for("login"))

        except Exception:
            app.logger.exception("Erro ao realizar login")
            flash("Erro ao entrar. Verifique os logs do servidor.")
            return redirect(url_for("login"))

    conteudo = """
        <h1>Meu Boletim</h1>
        <p>Entre na sua conta para acompanhar suas notas.</p>

        <form method="POST">
            <input type="email" name="email"
                placeholder="Seu e-mail" required>

            <input type="password" name="senha"
                placeholder="Sua senha" required>

            <button type="submit">Entrar</button>
        </form>

        <p>Ainda não tem conta?
        <a href="/criar-conta">Criar conta grátis</a></p>
    """

    return pagina("Login", conteudo)


# BOLETIM
@app.route("/boletim")
@proteger
def boletim():
    usuario = usuario_atual()

    if not usuario:
        session.clear()
        return redirect(url_for("login"))

    with conectar() as db:
        materias = db.execute("""
            SELECT id, nome, trimestre, nota
            FROM materias
            WHERE usuario_id = ?
            ORDER BY trimestre, nome
        """, (usuario["id"],)).fetchall()

    conteudo = f"""
        <h1>Meu boletim</h1>
        <p>Bem-vindo, {escape(usuario["email"])}</p>

        <h2>Adicionar matéria</h2>

        <form method="POST" action="/adicionar-materia">
            <input type="text" name="nome"
                placeholder="Nome da matéria" required>

            <select name="trimestre" required>
                <option value="1">1º trimestre</option>
                <option value="2">2º trimestre</option>
                <option value="3">3º trimestre</option>
            </select>

            <input type="number" name="nota"
                placeholder="Nota" min="0" max="100"
                step="0.1" required>

            <button type="submit">Adicionar matéria</button>
        </form>

        <h2>Minhas matérias</h2>
    """

    if not materias:
        conteudo += "<p>Você ainda não adicionou nenhuma matéria.</p>"

    for materia in materias:
        conteudo += f"""
            <div class="materia">
                <strong>{escape(materia["nome"])}</strong>
                <p>Trimestre: {materia["trimestre"]}º</p>
                <p>Nota: {materia["nota"]}</p>
                <form method="POST" action="/excluir-materia/{materia["id"]}">
                    <button type="submit">Excluir matéria</button>
                </form>
            </div>
        """

    return pagina("Meu boletim", conteudo)


# ADICIONAR MATÉRIA
@app.route("/adicionar-materia", methods=["POST"])
@proteger
def adicionar_materia():
    usuario = usuario_atual()

    try:
        nome = request.form.get("nome", "").strip()
        trimestre = int(request.form.get("trimestre", ""))
        nota = float(request.form.get("nota", ""))

        if not nome or trimestre not in (1, 2, 3) or not 0 <= nota <= 100:
            flash("Confira os dados informados.")
            return redirect(url_for("boletim"))

        with conectar() as db:
            db.execute("""
                INSERT INTO materias (usuario_id, nome, trimestre, nota)
                VALUES (?, ?, ?, ?)
            """, (usuario["id"], nome, trimestre, nota))

        flash("Matéria adicionada com sucesso.")

    except (ValueError, TypeError):
        flash("Informe uma nota e um trimestre válidos.")

    except Exception:
        app.logger.exception("Erro ao adicionar matéria")
        flash("Não foi possível adicionar a matéria.")

    return redirect(url_for("boletim"))


# EXCLUIR MATÉRIA
@app.route("/excluir-materia/<int:materia_id>", methods=["POST"])
@proteger
def excluir_materia(materia_id):
    usuario = usuario_atual()

    with conectar() as db:
        db.execute("""
            DELETE FROM materias
            WHERE id = ? AND usuario_id = ?
        """, (materia_id, usuario["id"]))

    flash("Matéria excluída.")
    return redirect(url_for("boletim"))


# SAIR DA CONTA
@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


# TESTE DO SERVIDOR
@app.route("/health")
def health():
    try:
        with conectar() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "banco": "conectado"}, 200
    except Exception:
        app.logger.exception("Falha no teste do banco")
        return {"status": "erro", "banco": "indisponivel"}, 500


if __name__ == "__main__":
    app.run(debug=False)
