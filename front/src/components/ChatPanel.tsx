import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatSearchResult, InstagramPostPreview } from "../types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  results?: ChatSearchResult[];
  instagramPost?: InstagramPostPreview | null;
}

interface ChatPanelProps {
  messages: ChatMessage[];
  sending: boolean;
  error: string | null;
  onSend: (message: string) => void;
}

export function ChatPanel({ messages, sending, error, onSend }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;
    setDraft("");
    onSend(message);
  };

  return (
    <main className="chat-shell">
      <header className="chat-header">
        <div className="chat-header__mark">M</div>
        <div>
          <h1 className="chat-header__title">Mijote</h1>
          <p className="chat-header__status">Agent recettes Instagram</p>
        </div>
      </header>

      <section className="chat-thread" aria-live="polite">
        <div className="chat-intro">
          <p className="chat-intro__eyebrow">Ton prochain plat commence ici</p>
          <h2>Parle-moi de ce que tu veux cuisiner.</h2>
          <p>Décris une envie, demande des idées ou colle directement un Reel Instagram.</p>
        </div>

        {messages.map((message) => (
          <article key={message.id} className={`chat-message chat-message--${message.role}`}>
            <div className="chat-message__bubble">{message.text}</div>

            {message.instagramPost && (
              <InstagramCard
                result={{
                  platform: "instagram",
                  url: message.instagramPost.source_url,
                  caption: message.instagramPost.description,
                }}
                thumbnail={message.instagramPost.thumbnail_url}
                onChoose={onSend}
                disabled={sending}
              />
            )}

            {!!message.results?.length && (
              <div className="result-grid">
                {message.results.map((result) => (
                  <InstagramCard
                    key={result.url}
                    result={result}
                    onChoose={onSend}
                    disabled={sending}
                  />
                ))}
              </div>
            )}
          </article>
        ))}

        {sending && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-message__bubble chat-message__bubble--typing">
              <span /><span /><span />
              <span className="sr-only">L'agent réfléchit</span>
            </div>
          </div>
        )}
        {error && <p className="chat-error">{error}</p>}
        <div ref={endRef} />
      </section>

      <form className="chat-composer" onSubmit={submit}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Une envie de plat ou un lien Instagram…"
          disabled={sending}
          aria-label="Message à l'agent"
        />
        <button type="submit" disabled={sending || !draft.trim()} aria-label="Envoyer">
          <SendIcon />
        </button>
      </form>
    </main>
  );
}

function InstagramCard({
  result,
  thumbnail,
  onChoose,
  disabled,
}: {
  result: ChatSearchResult;
  thumbnail?: string | null;
  onChoose: (message: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="result-card">
      {thumbnail && <img src={thumbnail} alt="Aperçu du Reel" />}
      <div className="result-card__body">
        <p>{result.caption || "Recette Instagram"}</p>
        <div className="result-card__actions">
          <a href={result.url} target="_blank" rel="noreferrer">Voir le Reel</a>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChoose(`Crée la recette de cette vidéo : ${result.url}`)}
          >
            Cuisiner
          </button>
        </div>
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m4 12 16-8-5 16-3-6-8-2Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="m12 14 8-10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
