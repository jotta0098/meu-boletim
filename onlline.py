
import os
import math
import random
import string
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "corrida-secreta")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

personagens = [
    "Lula",
    "Jair Bolsonaro",
    "Flávio Bolsonaro",
    "Javier Milei",
    "Donald Trump"
]

salas = {}

ITENS_INICIAIS = [
    {"id": 1, "x": 500, "y": 105, "ativo": True},
    {"id": 2, "x": 810, "y": 350, "ativo": True},
    {"id": 3, "x": 500, "y": 595, "ativo": True},
    {"id": 4, "x": 190, "y": 350, "ativo": True},
    {"id": 5, "x": 720, "y": 160, "ativo": True},
    {"id": 6, "x": 280, "y": 540, "ativo": True}
]


def nova_sala():
    return {
        "players": {},
        "items": [dict(item) for item in ITENS_INICIAIS]
    }


def gerar_codigo():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


@app.route("/")
def index():
    return render_template_string(HTML)


@socketio.on("create_room")
def create_room(data):
    codigo = gerar_codigo()

    while codigo in salas:
        codigo = gerar_codigo()

    salas[codigo] = nova_sala()

    entrar_na_sala({
        "room": codigo,
        "name": data.get("name", "Jogador"),
        "character": data.get("character", "Lula")
    })


@socketio.on("join_room")
def entrar_na_sala(data):
    codigo = str(data.get("room", "")).strip().upper()
    nome = str(data.get("name", "Jogador"))[:18]
    personagem = data.get("character", "Lula")

    if personagem not in personagens:
        personagem = "Lula"

    if not codigo or codigo not in salas:
        emit("error_message", "Sala não encontrada!")
        return

    sala = salas[codigo]

    if len(sala["players"]) >= 8:
        emit("error_message", "Essa sala está cheia!")
        return

    join_room(codigo)

    numero = len(sala["players"])
    angulo = math.pi + numero * 0.35

    jogador = {
        "id": request_id(),
        "name": nome,
        "character": personagem,
        "x": 500 + math.cos(angulo) * 320,
        "y": 350 + math.sin(angulo) * 190,
        "angle": angulo + math.pi / 2,
        "speed": 0,
        "inventory": None,
        "stun": 0
    }

    sala["players"][jogador["id"]] = jogador

    emit("joined", {
        "id": jogador["id"],
        "room": codigo,
        "players": list(sala["players"].values()),
        "items": sala["items"]
    })

    socketio.emit("player_joined", jogador, to=codigo, skip_sid=jogador["id"])
    socketio.emit("room_update", list(sala["players"].values()), to=codigo)


def request_id():
    from flask import request
    return request.sid


@socketio.on("move")
def move_player(data):
    codigo = data.get("room")
    if codigo not in salas:
        return

    jogador = salas[codigo]["players"].get(request_id())
    if not jogador:
        return

    for campo in ("x", "y", "angle", "speed"):
        try:
            jogador[campo] = float(data.get(campo, jogador[campo]))
        except (ValueError, TypeError):
            pass

    jogador["x"] = max(35, min(965, jogador["x"]))
    jogador["y"] = max(35, min(665, jogador["y"]))

    socketio.emit("player_moved", jogador, to=codigo, skip_sid=request_id())


@socketio.on("pickup")
def pickup(data):
    codigo = data.get("room")
    if codigo not in salas:
        return

    sala = salas[codigo]
    jogador = sala["players"].get(request_id())

    if not jogador or jogador.get("inventory"):
        return

    try:
        item_id = int(data.get("item_id"))
    except (ValueError, TypeError):
        return

    for item in sala["items"]:
        if item["id"] == item_id and item["ativo"]:
            distancia = math.hypot(
                jogador["x"] - item["x"],
                jogador["y"] - item["y"]
            )

            if distancia < 55:
                item["ativo"] = False
                jogador["inventory"] = random.choice(
                    ["🚀", "💣", "🍌", "⚡"]
                )

                socketio.emit("item_taken", {
                    "item_id": item_id,
                    "player_id": jogador["id"]
                }, to=codigo)

                emit("inventory", jogador["inventory"])

            break


@socketio.on("throw_item")
def throw_item(data):
    codigo = data.get("room")
    if codigo not in salas:
        return

    jogador = salas[codigo]["players"].get(request_id())

    if not jogador or not jogador.get("inventory"):
        return

    projetil = {
        "owner": jogador["id"],
        "x": jogador["x"],
        "y": jogador["y"],
        "angle": jogador["angle"],
        "item": jogador["inventory"]
    }

    jogador["inventory"] = None

    socketio.emit("projectile", projetil, to=codigo)
    emit("inventory", None)


@socketio.on("hit_player")
def hit_player(data):
    codigo = data.get("room")
    if codigo not in salas:
        return

    atacante = request_id()
    alvo = data.get("target")

    if alvo not in salas[codigo]["players"] or alvo == atacante:
        return

    socketio.emit("player_hit", {
        "target": alvo,
        "attacker": atacante
    }, to=codigo)


@socketio.on("disconnect")
def desconectar():
    sid = request_id()

    for codigo, sala in list(salas.items()):
        if sid in sala["players"]:
            del sala["players"][sid]

            socketio.emit("player_left", sid, to=codigo)
            socketio.emit(
                "room_update",
                list(sala["players"].values()),
                to=codigo
            )

            if not sala["players"]:
                del salas[codigo]

            break


HTML = r"""
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Presidential Kart</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>

<style>
* { box-sizing:border-box; }

body {
    margin:0;
    background:#101321;
    color:white;
    font-family:Arial,sans-serif;
    text-align:center;
}

header {
    padding:18px;
    background:#1b2036;
    border-bottom:2px solid #4d65ff;
}

header h1 {
    margin:0;
    color:#8294ff;
    font-size:30px;
}

header p { color:#b8bfd8; }

.tela {
    max-width:900px;
    margin:25px auto;
    padding:20px;
}

.painel {
    background:#20263e;
    padding:25px;
    border-radius:15px;
    margin-bottom:20px;
}

input,select {
    width:100%;
    padding:13px;
    margin:8px 0;
    border:0;
    border-radius:8px;
    background:#edf0ff;
}

button {
    padding:13px 18px;
    background:#5267ff;
    color:white;
    border:0;
    border-radius:8px;
    font-weight:bold;
    cursor:pointer;
    margin:5px;
}

button:hover { background:#374bd4; }

.personagens {
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
    gap:10px;
    margin:15px 0;
}

.personagem {
    padding:15px 5px;
    background:#303956;
    border:2px solid transparent;
    border-radius:10px;
    cursor:pointer;
}

.personagem.selecionado {
    border-color:#7186ff;
    background:#424f80;
}

.personagem .rosto {
    font-size:34px;
    margin-bottom:8px;
}

#jogo { display:none; }

canvas {
    width:100%;
    max-width:1000px;
    background:#267b43;
    border:3px solid #596aff;
    border-radius:12px;
    display:block;
    margin:15px auto;
}

.info {
    display:flex;
    justify-content:space-around;
    flex-wrap:wrap;
    gap:10px;
    background:#20263e;
    border-radius:10px;
    padding:14px;
}

.info div { font-weight:bold; }

#mensagem { color:#ffcc55; min-height:25px; }

#ranking {
    text-align:left;
    background:#20263e;
    border-radius:10px;
    padding:15px;
    margin-top:15px;
}

.controles {
    color:#c2c9df;
    line-height:1.8;
}

@media(max-width:600px) {
    .tela { padding:8px; }
    canvas { margin-top:10px; }
}
</style>
</head>

<body>

<header>
    <h1>🏎️ PRESIDENTIAL KART</h1>
    <p>Entre na pista e vença seus adversários!</p>
</header>

<div class="tela">

<div id="inicio" class="painel">
    <h2>Escolha seu piloto</h2>

    <input id="nome" placeholder="Digite seu apelido" maxlength="18">

    <div class="personagens">
        <div class="personagem selecionado" onclick="escolher('Lula',this)">
            <div class="rosto">👨🏻</div>
            Lula
        </div>

        <div class="personagem" onclick="escolher('Jair Bolsonaro',this)">
            <div class="rosto">👨🏻‍🦳</div>
            Jair Bolsonaro
        </div>

        <div class="personagem" onclick="escolher('Flávio Bolsonaro',this)">
            <div class="rosto">👨🏻</div>
            Flávio Bolsonaro
        </div>

        <div class="personagem" onclick="escolher('Javier Milei',this)">
            <div class="rosto">🧔🏻</div>
            Javier Milei
        </div>

        <div class="personagem" onclick="escolher('Donald Trump',this)">
            <div class="rosto">👱🏻‍♂️</div>
            Donald Trump
        </div>
    </div>

    <button onclick="criarSala()">CRIAR SALA</button>

    <hr style="border-color:#414968;margin:25px 0">

    <h3>Entrar na sala de um amigo</h3>

    <input id="codigo" placeholder="Código da sala" maxlength="5">

    <button onclick="entrarSala()">ENTRAR NA CORRIDA</button>

    <p id="mensagem"></p>
</div>


<div id="jogo">

    <div class="info">
        <div>🏁 Sala: <span id="salaAtual">-----</span></div>
        <div>🚗 Velocidade: <span id="velocidade">0</span></div>
        <div>🎁 Item: <span id="inventario">Nenhum</span></div>
    </div>

    <canvas id="canvas" width="1000" height="700"></canvas>

    <div class="painel">
        <h3>Controles</h3>
        <div class="controles">
            W ou ↑ = Acelerar<br>
            S ou ↓ = Frear<br>
            A ou ← = Virar para esquerda<br>
            D ou → = Virar para direita<br>
            ESPAÇO = Lançar objeto
        </div>
        <button onclick="copiarCodigo()">COPIAR CÓDIGO DA SALA</button>
        <button onclick="location.reload()">SAIR DA CORRIDA</button>
    </div>

    <div id="ranking">
        <h3>🏆 Jogadores na sala</h3>
        <div id="listaJogadores">Aguardando jogadores...</div>
    </div>

</div>

</div>

<script>
const socket = io();

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

let personagem = "Lula";
let meuId = null;
let sala = null;
let jogadores = {};
let itens = [];
let inventario = null;
let projeteis = [];
let teclas = {};
let velocidade = 0;
let angulo = 0;
let x = 180;
let y = 350;
let travado = 0;
let ultimoEnvio = 0;

const cores = {
    "Lula":"#2386ff",
    "Jair Bolsonaro":"#f2d43d",
    "Flávio Bolsonaro":"#ff963d",
    "Javier Milei":"#e7e7ed",
    "Donald Trump":"#e64b4b"
};

function escolher(nome, elemento) {
    personagem = nome;

    document.querySelectorAll(".personagem").forEach(el =>
        el.classList.remove("selecionado")
    );

    elemento.classList.add("selecionado");
}

function mostrarMensagem(texto) {
    document.getElementById("mensagem").innerText = texto;
}

function criarSala() {
    socket.emit("create_room", {
        name: document.getElementById("nome").value || "Jogador",
        character: personagem
    });
}

function entrarSala() {
    socket.emit("join_room", {
        room: document.getElementById("codigo").value,
        name: document.getElementById("nome").value || "Jogador",
        character: personagem
    });
}

socket.on("error_message", mostrarMensagem);

socket.on("joined", data => {
    meuId = data.id;
    sala = data.room;
    itens = data.items;

    document.getElementById("inicio").style.display = "none";
    document.getElementById("jogo").style.display = "block";
    document.getElementById("salaAtual").innerText = sala;

    jogadores = {};

    data.players.forEach(p => {
        jogadores[p.id] = p;

        if (p.id === meuId) {
            x = p.x;
            y = p.y;
            angulo = p.angle;
        }
    });

    atualizarRanking();
    desenhar();
});

socket.on("player_joined", p => {
    jogadores[p.id] = p;
    atualizarRanking();
});

socket.on("room_update", lista => {
    jogadores = {};
    lista.forEach(p => jogadores[p.id] = p);
    atualizarRanking();
});

socket.on("player_moved", p => {
    if (p.id !== meuId) jogadores[p.id] = p;
});

socket.on("player_left", id => {
    delete jogadores[id];
    atualizarRanking();
});

socket.on("item_taken", data => {
    const item = itens.find(i => i.id === data.item_id);
    if (item) item.ativo = false;
});

socket.on("inventory", item => {
    inventario = item;
    document.getElementById("inventario").innerText = item || "Nenhum";
});

socket.on("projectile", p => {
    projeteis.push({
        ...p,
        distancia:0,
        atingidos:[]
    });
});

socket.on("player_hit", data => {
    if (data.target === meuId) {
        travado = 75;
        velocidade = -2;
        mostrarMensagem("💥 Você foi atingido!");
    }
});

function copiarCodigo() {
    navigator.clipboard.writeText(sala);
    mostrarMensagem("Código da sala copiado: " + sala);
}

function atualizarRanking() {
    const lista = Object.values(jogadores);

    document.getElementById("listaJogadores").innerHTML =
        lista.map((p,i) =>
            `<p>${i+1}. ${p.name} — ${p.character}</p>`
        ).join("");
}

function desenharPista() {
    ctx.fillStyle = "#267b43";
    ctx.fillRect(0,0,1000,700);

    // Parte externa da pista
    ctx.fillStyle = "#343944";
    ctx.beginPath();
    ctx.ellipse(500,350,440,290,0,0,Math.PI*2);
    ctx.fill();

    // Centro da pista
    ctx.fillStyle = "#267b43";
    ctx.beginPath();
    ctx.ellipse(500,350,240,125,0,0,Math.PI*2);
    ctx.fill();

    // Faixas de limite
    ctx.strokeStyle = "white";
    ctx.lineWidth = 5;

    ctx.beginPath();
    ctx.ellipse(500,350,440,290,0,0,Math.PI*2);
    ctx.stroke();

    ctx.beginPath();
    ctx.ellipse(500,350,240,125,0,0,Math.PI*2);
    ctx.stroke();

    // Linha de chegada
    ctx.save();
    ctx.translate(500, 640);

    for(let i=0;i<10;i++) {
        ctx.fillStyle = i%2 ? "white" : "black";
        ctx.fillRect(-50+i*10,0,10,15);
    }

    ctx.restore();

    // Decoração do centro
    ctx.fillStyle = "#2d9550";
    ctx.font = "bold 27px Arial";
    ctx.textAlign = "center";
    ctx.fillText("PRESIDENTIAL KART",500,345);
}

function desenharCarro(p, eu=false) {
    ctx.save();

    ctx.translate(p.x,p.y);
    ctx.rotate(p.angle);

    ctx.fillStyle = cores[p.character] || "#ffffff";

    // Corpo do carro
    ctx.beginPath();
    ctx.roundRect(-23,-13,46,26,8);
    ctx.fill();

    // Vidro
    ctx.fillStyle = "#18243b";
    ctx.fillRect(-7,-10,16,20);

    // Rodas
    ctx.fillStyle = "#080808";
    ctx.fillRect(-17,-17,12,6);
    ctx.fillRect(7,-17,12,6);
    ctx.fillRect(-17,11,12,6);
    ctx.fillRect(7,11,12,6);

    // Frente
    ctx.fillStyle = "#ffe58a";
    ctx.fillRect(15,-8,5,5);
    ctx.fillRect(15,3,5,5);

    ctx.restore();

    ctx.fillStyle = eu ? "#ffff70" : "white";
    ctx.font = "bold 13px Arial";
    ctx.textAlign = "center";
    ctx.fillText(p.character,p.x,p.y-25);
    ctx.font = "11px Arial";
    ctx.fillText(p.name || "",p.x,p.y-39);
}

function desenharItens() {
    itens.forEach(item => {
        if (!item.ativo) return;

        ctx.fillStyle = "#ffcc33";
        ctx.beginPath();
        ctx.arc(item.x,item.y,17,0,Math.PI*2);
        ctx.fill();

        ctx.fillStyle = "#222";
        ctx.font = "20px Arial";
        ctx.textAlign = "center";
        ctx.fillText("?",item.x,item.y+7);
    });
}

function desenharProjeteis() {
    projeteis.forEach(p => {
        ctx.font = "24px Arial";
        ctx.textAlign = "center";
        ctx.fillText(p.item,p.x,p.y);
    });
}

function dentroDaPista(nx,ny) {
    const exterior =
        ((nx-500)**2 / 440**2) +
        ((ny-350)**2 / 290**2);

    const interior =
        ((nx-500)**2 / 240**2) +
        ((ny-350)**2 / 125**2);

    return exterior <= 1 && interior >= 1;
}

function atualizar() {
    if (!meuId || !jogadores[meuId]) return;

    if (travado > 0) {
        travado--;
        velocidade *= 0.94;
    } else {
        if (teclas["ArrowUp"] || teclas["w"] || teclas["W"]) {
            velocidade += 0.16;
        }

        if (teclas["ArrowDown"] || teclas["s"] || teclas["S"]) {
            velocidade -= 0.13;
        }

        velocidade *= 0.985;
        velocidade = Math.max(-2.5,Math.min(6,velocidade));

        if (Math.abs(velocidade) > 0.15) {
            let curva = velocidade > 0 ? 1 : -1;

            if (teclas["ArrowLeft"] || teclas["a"] || teclas["A"]) {
                angulo -= 0.045 * curva;
            }

            if (teclas["ArrowRight"] || teclas["d"] || teclas["D"]) {
                angulo += 0.045 * curva;
            }
        }
    }

    let nx = x + Math.cos(angulo)*velocidade;
    let ny = y + Math.sin(angulo)*velocidade;

    if (dentroDaPista(nx,ny)) {
        x = nx;
        y = ny;
    } else {
        velocidade *= 0.75;
    }

    jogadores[meuId].x = x;
    jogadores[meuId].y = y;
    jogadores[meuId].angle = angulo;
    jogadores[meuId].speed = velocidade;

    document.getElementById("velocidade").innerText =
        Math.round(Math.abs(velocidade)*20);

    // Procurar caixas de itens
    if (!inventario) {
        itens.forEach(item => {
            if (!item.ativo) return;

            if (Math.hypot(x-item.x,y-item.y) < 28) {
                socket.emit("pickup", {
                    room:sala,
                    item_id:item.id
                });
            }
        });
    }

    // Movimento dos projéteis
    projeteis.forEach(p => {
        p.x += Math.cos(p.angle)*8;
        p.y += Math.sin(p.angle)*8;
        p.distancia += 8;

        if (p.owner !== meuId && !p.atingidos.includes(meuId)) {
            if (Math.hypot(x-p.x,y-p.y) < 25) {
                p.atingidos.push(meuId);

                socket.emit("hit_player", {
                    room:sala,
                    target:meuId
                });
            }
        }

        Object.values(jogadores).forEach(j => {
            if (j.id === p.owner || p.atingidos.includes(j.id)) return;

            if (Math.hypot(j.x-p.x,j.y-p.y) < 25) {
                p.atingidos.push(j.id);

                if (meuId === p.owner) {
                    socket.emit("hit_player", {
                        room:sala,
                        target:j.id
                    });
                }
            }
        });
    });

    projeteis = projeteis.filter(p =>
        p.distancia < 650 &&
        p.x > 0 && p.x < 1000 &&
        p.y > 0 && p.y < 700
    );

    let agora = Date.now();

    if (agora - ultimoEnvio > 50) {
        socket.emit("move", {
            room:sala,
            x:x,
            y:y,
            angle:angulo,
            speed:velocidade
        });

        ultimoEnvio = agora;
    }
}

function desenhar() {
    if (!meuId) return;

    atualizar();

    desenharPista();
    desenharItens();

    Object.values(jogadores).forEach(p => {
        desenharCarro(p,p.id===meuId);
    });

    desenharProjeteis();

    requestAnimationFrame(desenhar);
}

document.addEventListener("keydown",e => {
    teclas[e.key] = true;

    if (e.code === "Space") {
        e.preventDefault();

        if (inventario) {
            socket.emit("throw_item",{room:sala});
        }
    }
});

document.addEventListener("keyup",e => {
    teclas[e.key] = false;
});
</script>

</body>
</html>
"""


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        allow_unsafe_werkzeug=True
    )
