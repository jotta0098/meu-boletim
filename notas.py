
import sqlite3
from functools import wraps
from flask import Flask, request, redirect, session, flash, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape

app = Flask(__name__)
app.secret_key = "troque-por-uma-chave-secreta"

BANCO = "boletim.db"

# PERSONALIZE SEUS DADOS
CHAVE_PIX = "COLOQUE_SUA_CHAVE_PIX"
NOME_PIX = "SEU NOME"
VALOR = "10,00"
SENHA_ADMIN = "Jotta@123"


def conectar():
    banco = sqlite3.connect(BANCO)
    banco.row_factory = sqlite3.Row
    return banco


def criar_banco():
    with conectar() as banco:
        banco.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                status TEXT DEFAULT 'pendente',
                comprovante TEXT
            )
        """)


def usuario_atual():
    if "usuario" not in session:
        return None

    with conectar() as banco:
        return banco.execute(
            "SELECT * FROM usuarios WHERE id = ?",
            (session["usuario"],)
        ).fetchone()


def proteger(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if not usuario_atual():
            return redirect("/login")
        return funcao(*args, **kwargs)
    return verificar


def liberar(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        usuario = usuario_atual()

        if not usuario:
            return redirect("/login")

        if usuario["status"] != "aprovado":
            return redirect("/pagamento")

        return funcao(*args, **kwargs)
    return verificar


def pagina(titulo, conteudo):
    usuario = usuario_atual()

    menu = """
    <a href="/">Início</a>
    <a href="/criar-conta">Criar conta</a>
    <a href="/login">Login</a>
    """

    if usuario:
        menu = """
        <a href="/boletim">Meu boletim</a>
        <a href="/sair">Sair</a>
        """

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ titulo }} - Meu Boletim</title>
    <style>
    * { box-sizing: border-box; }
    body {
        margin: 0;
        background: #f1f4fa;
        font-family: Arial, sans-serif;
        color: #18233a;
    }
    header {
        background: #101b35;
        color: white;
        padding: 22px 8%;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 15px;
    }
    header strong { font-size: 22px; }
    header a {
        color: white;
        text-decoration: none;
        margin-left: 15px;
    }
    main {
        max-width: 750px;
        margin: 55px auto;
        padding: 0 18px;
    }
    .card {
        background: white;
        padding: 35px;
        border-radius: 18px;
        box-shadow: 0 8px 30px #00000010;
    }
    h1 { font-size: 30px; }
    p { color: #647087; line-height: 1.6; }
    input, textarea {
        width: 100%;
        padding: 14px;
        border: 1px solid #d9dfeb;
        border-radius: 9px;
        margin: 8px 0 18px;
        font-size: 15px;
    }
    label { font-weight: bold; }
    button, .botao {
        display: inline-block;
        background: #315efb;
        color: white;
        padding: 14px 20px;
        border: none;
        border-radius: 9px;
        text-decoration: none;
        cursor: pointer;
        font-weight: bold;
    }
    .pix {
        background: #f0f3ff;
        padding: 18px;
        border-radius: 12px;
        overflow-wrap: anywhere;
    }
    .mensagem {
        background: #fff1c9;
        padding: 13px;
        border-radius: 9px;
        margin-bottom: 15px;
    }
    table { width: 100%; border-collapse: collapse; }
    td, th {
        padding: 10px;
        border-bottom: 1px solid #ddd;
        text-align: left;
    }
    </style>
    </head>
    <body>
    <header>
        <strong>MEU BOLETIM</strong>
        <nav>{{ menu|safe }}</nav>
    </header>
    <main>
        {% for mensagem in get_flashed_messages() %}
            <div class="mensagem">{{ mensagem }}</div>
        {% endfor %}
        {{ conteudo|safe }}
    </main>
    </body>
    </html>
    """, titulo=titulo, conteudo=conteudo, menu=menu)


@app.route("/")
def inicio():
    if usuario_atual():
        usuario = usuario_atual()
        if usuario["status"] == "aprovado":
            return redirect("/boletim")
        return redirect("/pagamento")

    return pagina("Início", """
    <div class="card">
        <h1>Bem-vindo ao Meu Boletim!</h1>
        <p>Organize suas notas escolares em um só lugar.</p>
        <a class="botao" href="/criar-conta">CRIAR CONTA</a>
        <a class="botao" href="/login">FAZER LOGIN</a>
    </div>
    """)


@app.route("/criar-conta", methods=["GET", "POST"])
def criar_conta():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        if not nome or len(senha) < 6:
            flash("Preencha os campos. A senha deve ter pelo menos 6 caracteres.")
        else:
            try:
                with conectar() as banco:
                    cursor = banco.execute("""
                        INSERT INTO usuarios (nome, email, senha)
                        VALUES (?, ?, ?)
                    """, (nome, email, generate_password_hash(senha)))

                    session["usuario"] = cursor.lastrowid

                return redirect("/pagamento")

            except sqlite3.IntegrityError:
                flash("Este e-mail já está cadastrado.")

    return pagina("Criar conta", """
    <div class="card">
        <h1>Criar minha conta</h1>
        <form method="POST">
            <label>Nome completo</label>
            <input name="nome" required>

            <label>E-mail</label>
            <input name="email" type="email" required>

            <label>Senha</label>
            <input name="senha" type="password" minlength="6" required>

            <button>Cadastrar e continuar</button>
        </form>
        <p>Já possui conta? <a href="/login">Entre aqui</a>.</p>
    </div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        with conectar() as banco:
            usuario = banco.execute(
                "SELECT * FROM usuarios WHERE email = ?", (email,)
            ).fetchone()

        if usuario and check_password_hash(usuario["senha"], senha):
            session["usuario"] = usuario["id"]

            if usuario["status"] == "aprovado":
                return redirect("/boletim")

            return redirect("/pagamento")

        flash("E-mail ou senha incorretos.")

    return pagina("Login", """
    <div class="card">
        <h1>Entrar na minha conta</h1>
        <form method="POST">
            <label>E-mail</label>
            <input name="email" type="email" required>

            <label>Senha</label>
            <input name="senha" type="password" required>

            <button>ENTRAR</button>
        </form>
        <p>Não tem conta? <a href="/criar-conta">Cadastre-se</a>.</p>
    </div>
    """)


@app.route("/pagamento", methods=["GET", "POST"])
@proteger
def pagamento():
    usuario = usuario_atual()

    if usuario["status"] == "aprovado":
        return redirect("/boletim")

    if request.method == "POST":
        comprovante = request.form["comprovante"].strip()

        if comprovante:
            with conectar() as banco:
                banco.execute("""
                    UPDATE usuarios
                    SET comprovante = ?, status = 'em análise'
                    WHERE id = ?
                """, (comprovante, usuario["id"]))

            flash("Comprovante enviado! Aguarde a aprovação.")
            return redirect("/pagamento")

    return pagina("Pagamento", f"""
    <div class="card">
        <h1>Pagamento</h1>
        <p>Para liberar seu acesso, realize o pagamento via Pix.</p>

        <div class="pix">
            <h2>R$ {VALOR}</h2>
            <p><strong>Chave Pix:</strong> {escape(CHAVE_PIX)}</p>
            <p><strong>Recebedor:</strong> {escape(NOME_PIX)}</p>
        </div>

        <p>Status: <strong>{escape(usuario["status"])}</strong></p>

        <form method="POST">
            <label>Link ou identificação do comprovante</label>
            <textarea name="comprovante" required
            placeholder="Cole o link ou informe os dados do comprovante"></textarea>
            <button>ENVIAR COMPROVANTE</button>
        </form>

        <p>O administrador verificará o pagamento antes de liberar a conta.</p>
    </div>
    """)


@app.route("/boletim")
@liberar
def boletim():
    usuario = usuario_atual()

    return pagina("Meu boletim", f"""
    <div class="card">
        <h1>Olá, {escape(usuario["nome"])}!</h1>
        <p>Sua conta foi aprovada.</p>
        <h2>Meu boletim escolar</h2>
        <p>Seu acesso está liberado. Aqui ficará seu controle de notas.</p>
    </div>
    """)


@app.route("/sair")
def sair():
    session.clear()
    return redirect("/")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["senha"] == SENHA_ADMIN:
            session["admin"] = True
            return redirect("/admin")

        flash("Senha incorreta.")

    return pagina("Administração", """
    <div class="card">
        <h1>Área administrativa</h1>
        <form method="POST">
            <label>Senha do administrador</label>
            <input name="senha" type="password" required>
            <button>ENTRAR</button>
        </form>
    </div>
    """)


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin/login")

    with conectar() as banco:
        usuarios = banco.execute(
            "SELECT * FROM usuarios ORDER BY id DESC"
        ).fetchall()

    linhas = ""

    for u in usuarios:
        comprovante = escape(u["comprovante"] or "Não enviado")
        acao = ""

        if u["status"] != "aprovado":
            acao = f"""
            <form method="POST" action="/admin/aprovar/{u['id']}">
                <button>Aprovar conta</button>
            </form>
            """

        linhas += f"""
        <tr>
            <td>{escape(u['nome'])}</td>
            <td>{escape(u['email'])}</td>
            <td>{escape(u['status'])}</td>
            <td>{comprovante}</td>
            <td>{acao}</td>
        </tr>
        """

    return pagina("Administração", f"""
    <div class="card">
        <h1>Gerenciar pagamentos</h1>
        <p>Confira o recebimento no banco antes de aprovar qualquer conta.</p>
        <div style="overflow-x:auto">
        <table>
            <tr>
                <th>Nome</th><th>E-mail</th><th>Status</th>
                <th>Comprovante</th><th>Ação</th>
            </tr>
            {linhas}
        </table>
        </div>
    </div>
    """)


@app.route("/admin/aprovar/<int:id>", methods=["POST"])
def aprovar(id):
    if not session.get("admin"):
        return redirect("/admin/login")

    with conectar() as banco:
        banco.execute(
            "UPDATE usuarios SET status = 'aprovado' WHERE id = ?", (id,)
        )

    flash("Conta aprovada.")
    return redirect("/admin")


if __name__ == "__main__":
    criar_banco()
    app.run(debug=True)
