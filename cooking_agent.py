import cv2
import time
import threading
from google import genai
import itertools
import json
import os

try:
    import speech_recognition as sr
    HAS_SPEECH = True
except ImportError:
    HAS_SPEECH = False
    print("SpeechRecognition not installed. Use Spacebar for 'done'.")

import tempfile

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False
    print("gTTS not installed. Fallback to Mac robotic voice.")

def speak(text):
    """Fonction TTS fluide utilisant Google Text-to-Speech."""
    def run_tts():
        if HAS_GTTS:
            try:
                tts = gTTS(text=text, lang='en')
                fd, path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                tts.save(path)
                os.system(f"afplay {path}")
                os.remove(path)
            except Exception as e:
                # Fallback si pas de connexion internet
                os.system(f"say '{text}'")
        else:
            os.system(f"say '{text}'")
            
    threading.Thread(target=run_tts, daemon=True).start()

# ==========================================
# CONFIGURATION GEMINI
# ==========================================
# Chargement du fichier .env
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key_env, val = line.strip().split('=', 1)
                os.environ[key_env.strip()] = val.strip().strip('"\'')

API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3")
]
# On garde uniquement les clés qui existent
API_KEYS = [k for k in API_KEYS if k]
# En utilisant 5 modèles différents, on multiplie le quota quotidien par 5 !
MODELS = [
    "gemini-3.5-flash-lite"
]
INTERVALLE_ANALYSE = 4.5          # 4.5 sec = ~13 req/min

clients = [genai.Client(api_key=key) for key in API_KEYS]
client_cycle = itertools.cycle(clients)
model_cycle = itertools.cycle(MODELS)

# ==========================================
# CONFIGURATION RECETTE
# ==========================================
with open("recipe_compote.json", "r", encoding="utf-8") as f:
    recipe = json.load(f)
steps = recipe["steps"]

# Calcul dynamique de tous les objets qui existent dans la recette
all_recipe_objects = set()
for step in steps:
    for obj in step.get("required_objects", []):
        all_recipe_objects.add(obj.lower())

current_step_idx = 0
step_announced = False
last_error_time = 0

# Variables globales multithreading
ingredients_detectes = ""
is_analyzing = False
last_analysis_time = 0
voice_trigger = False
erreur_affichage = ""

def listen_for_done():
    """Écoute en permanence le mot 'terminé' en arrière-plan."""
    global voice_trigger
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source)
            while True:
                try:
                    audio = r.listen(source, timeout=2, phrase_time_limit=3)
                    text = r.recognize_google(audio, language="en-US").lower()
                    print("🎤 You said :", text)
                    if any(phrase in text for phrase in ["done", "i'm done", "finished", "i am done", "next"]):
                        voice_trigger = True
                except:
                    continue
    except Exception as e:
        print("Microphone Error:", e)

if HAS_SPEECH:
    threading.Thread(target=listen_for_done, daemon=True).start()

def appel_gemini_vision(frame_bgr):
    global ingredients_detectes, is_analyzing, last_error_time
    try:
        frame_resized = cv2.resize(frame_bgr, (640, 480))
        _, buffer = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        image_bytes = buffer.tobytes()

        client_actuel = next(client_cycle)
        model_actuel = next(model_cycle)
        
        # Envoi à Gemini (rotation ultra rapide sur les modèles et les clés)
        response = client_actuel.models.generate_content(
            model=model_actuel,
            contents=[
                genai.types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                "Identify ONLY the food ingredients and kitchen utensils that the user is holding or manipulating. "
                "Do NOT list background elements (table, wall, empty plate, person, hand). "
                "Reply ONLY with a short comma-separated list (ex: apple, knife). "
                "Use simple words in singular form (lowercase). If nothing is relevant, reply nothing."
            ]
        )
        
        # Effacer l'affichage d'erreur précédente à chaque nouvelle analyse
        global erreur_affichage
        erreur_affichage = ""
        
        if response.text:
            texte_brut = response.text.strip().lower()
            ingredients_detectes = texte_brut
            
            # --- VERIFICATION DYNAMIQUE DES ERREURS ---
            if current_step_idx < len(steps):
                # 1. Calculer ce qui est autorisé jusqu'à cette étape incluse
                allowed_objects = set()
                for i in range(current_step_idx + 1):
                    for obj in steps[i].get("required_objects", []):
                        allowed_objects.add(obj.lower())
                
                # 2. Vérifier chaque objet détecté par Gemini
                objets_detectes = [x.strip() for x in texte_brut.split(',') if x.strip()]
                
                for obj in objets_detectes:
                    # On cherche si le mot clé (ex: "pomme") est dans le texte détecté
                    # On utilise une vérification simple
                    if obj not in allowed_objects:
                        # Est-ce que l'objet est utile plus tard ?
                        # Pour gérer les synonymes, on vérifie avec une inclusion
                        is_in_recipe_somewhere = any(req in obj or obj in req for req in all_recipe_objects)
                        
                        if is_in_recipe_somewhere and (time.time() - last_error_time > 6.0):
                            last_error_time = time.time()
                            erreur_affichage = f"{obj} detected too early!"
                            speak(f"This is not the time to use the {obj}, put it aside for now.")
                            break 
                            
                        elif not is_in_recipe_somewhere and (time.time() - last_error_time > 6.0):
                            last_error_time = time.time()
                            erreur_affichage = f"{obj} not in recipe!"
                            speak(f"You don't need the {obj} for this recipe.")
                            break
                            
    except Exception as e:
        print(f"API Error: {e}")
        ingredients_detectes = "API Error"
    finally:
        is_analyzing = False

# ==========================================
# BOUCLE PRINCIPALE (WEBCAM)
# ==========================================
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Cannot access the webcam.")
    exit()

print("🚀 Starting Cooking Assistant (Say 'DONE' or press Space to validate step, 'q' to quit)...")

while cap.isOpened() and current_step_idx < len(steps):
    success, frame = cap.read()
    if not success:
        break
        
    step = steps[current_step_idx]
    
    # Annonce vocale de l'étape au début
    if not step_announced:
        speak(step["instruction"])
        step_announced = True

    current_time = time.time()
    
    # Déclenchement automatique de Gemini
    if not is_analyzing and (current_time - last_analysis_time > INTERVALLE_ANALYSE):
        last_analysis_time = current_time
        is_analyzing = True
        thread = threading.Thread(target=appel_gemini_vision, args=(frame.copy(),))
        thread.daemon = True
        thread.start()

    # Affichage sur l'image
    h, w, _ = frame.shape
    cv2.rectangle(frame, (0, 0), (w, 110), (0, 0, 0), -1)
    
    status_text = f"Step {step['id']} / {len(steps)}"
    cv2.putText(frame, status_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    statut = "[Analyzing...]" if is_analyzing else "[OK]"
    cv2.putText(frame, f"Gemini {statut}: {ingredients_detectes}", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    # Check si on a des objets interdits pour l'affichage visuel
    if erreur_affichage:
        cv2.putText(frame, f"ERROR: {erreur_affichage}", (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        cv2.putText(frame, "Say 'DONE' or Space to validate", (15, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.imshow("Cooking Assistant - Gemini", frame)

    key = cv2.waitKey(1) & 0xFF
    
    if key == ord(' ') or voice_trigger:
        speak("Great, moving on to the next step.")
        current_step_idx += 1
        step_announced = False
        ingredients_detectes = ""
        voice_trigger = False
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
if current_step_idx >= len(steps):
    speak("Congratulations, the recipe is complete!")