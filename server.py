import socket
from _thread import *
import sys
import time
import json
import os

#json file management
def load_log():
    if not os.path.exists("game_log.json"):
        with open("game_log.json", "w") as f:
            json.dump([], f)
    with open("game_log.json", "r") as f:
        return json.load(f)

def save_games(data):
    #formats the json file with any new necessary data
    with open("game_log.json", "w") as f:
        json.dump(data, f, indent=2)

def add_log(hname, pword):
    data = load_log()
    for game in data:
        if game["host_name"].lower() == hname.lower():
            return False  # Duplicate game
    new_game = {
        "host_name": hname,
        "password": pword,
        "active": True,
        "players_connected": 1
    }
    data.append(new_game)
    save_games(data)
    return True

def join_game_log(hname, pword):
    data = load_log()
    for game in data:
        if game["host_name"].lower() == hname.lower() and game["password"] == pword and game["active"]:
            game["players_connected"] += 1
            if game["players_connected"] >= 2:
                game["active"] = False  # Game ready
            save_games(data)
            return True
    return False
#end of json mgment


active_rooms = []
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server = '192.168.0.42'
port = 5555
game_started = False
it_player_id = 0
last_tag_time = 0
tag_cooldown = 2.0 #time in seconds

try:
    s.bind((server, port))
except socket.error as e:
    print(str(e))

s.listen(2)
print("Waiting for a connection")

#set the two players positions
pos = ["0:500,200", "1:800,200"]
#store client connections
clients = []
#link player id to a connection
player_sockets = {}

def broadcast_start():
    global clients
    print("Broadcasting START to all clients")
    for i in clients:
        try:
            i.sendall("START".encode())
        except:
            pass

def threaded_client(conn, player_id):
    global pos, game_started, clients, player_sockets, player_count, it_player_id, active_rooms, last_tag_time, tag_cooldown

    current_room_name = None
    #save connection
    player_sockets[player_id] = conn
    #send player their id
    conn.send(str(player_id).encode())
    game_duration = 60


    while True:
        try:
            raw_data = conn.recv(2048)
            if not raw_data:
                break
            reply = raw_data.decode('utf-8')
            print(f"Received from player {player_id}: {reply}")

            #manage game creations
            if reply.startswith("CREATE:"):
                _, name, pword, = reply.split(":")
                if add_log(name, pword):
                    current_room_name = name
                    conn.send("OK".encode())
                else:
                    conn.send("ERROR:DUPLICATE".encode())

            #manage search for rooms
            elif reply.startswith("JOIN:"):
                try:
                    parts = reply.split(":")
                    if len(parts) < 3:
                        conn.send("ERROR:INVALID FORMAT".encode())
                        continue

                    target_name = parts[1]
                    target_pword = parts[2]

                    log_data = load_log()
                    found_game = False

                    for game in log_data:
                        name_match = game["host_name"].lower() == target_name.lower()
                        pass_match = str(game["password"]).lower() == str(target_pword)
                        is_active = game["active"]

                        if name_match and pass_match and is_active:
                            current_room_name = target_name
                            game["players_connected"] += 1
                            if game["players_connected"] >= 2:
                                game["active"] = False
                                pass
                            save_games(log_data)
                            found_game = True
                            break
                    if found_game:
                        conn.send("OK".encode())
                    else:
                        conn.send("ERROR:Game not found".encode())
                except Exception as e:
                    print(f"Join error: {e}")
                    conn.send("ERROR:Exception".encode())

            else:
                send_deafult_reply = True

                players_in_my_room = 1
                if current_room_name:
                    log_data = load_log()
                    for game in log_data:
                        if game["host_name"].lower() == current_room_name:
                            players_in_my_room = game["players_connected"]
                            break

            #Gameplay, no longer menu
                if reply.startswith("TAG:"):
                    current_time = time.time()
                    tagger_id = int(reply.split(":")[1])
                    if tagger_id == it_player_id and current_time - last_tag_time > tag_cooldown:
                        it_player_id = 1 - tagger_id
                        last_tag_time = current_time

                elif reply == "START":
                    game_started = True
                    start_time = time.time()
                    #make game inactive, others cant join
                    log_data = load_log()
                    if log_data:
                        log_data[-1]["active"] = False
                        save_games(log_data)
                    broadcast_start()
                    send_deafult_reply = False
                    continue
                elif reply[0].isdigit():
                    arr = reply.split(":")
                    pid = int(arr[0])
                    pos[pid] = reply

                if send_deafult_reply:
                    #calc time left
                    if game_started:
                        elapsed = time.time() - start_time
                        time_left = max(0, game_duration - elapsed)
                    else:
                        time_left = game_duration

                    other_id = 1-player_id
                    current_count = 2 if game_started else 1
                    reply_data = f"{pos[other_id]}|{it_player_id}|{players_in_my_room}|{int(time_left)}"
                    conn.sendall(reply_data.encode())
        except Exception as e:
            print("Connection error: ", e)
            break
    print(f"Connection with player{player_id} closed")
    pos[player_id] = f"{player_id}:-1-1"
    conn.close()
    if conn in clients:
        clients.remove(conn)

current_id_counter = 0

while True:
    conn, addr = s.accept()
    print("Connected to: ", addr)
    clients.append(conn)
    #manage 3rd connection (modulus)
    player_id_safe = current_id_counter % 2
    start_new_thread(threaded_client, (conn,player_id_safe))
    current_id_counter += 1