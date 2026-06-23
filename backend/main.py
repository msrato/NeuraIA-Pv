
from mind import decidir_resposta

print("Neura online. Digite 'sair' para encerrar.")

while True:
    user_input = input("Você: ")

    if user_input.lower() == "sair":
        print("Neura: desligando...")
        break

    # Decide o que responder
    resposta = decidir_resposta(user_input)

    print("Neura:", resposta)

