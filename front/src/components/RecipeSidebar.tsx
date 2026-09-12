import type { Recipe } from "../types";

interface RecipeSidebarProps {
  recipe: Recipe;
  currentStepIndex: number;
  cameraActive: boolean;
}

export function RecipeSidebar({ recipe, currentStepIndex, cameraActive }: RecipeSidebarProps) {
  return (
    <aside className="sidebar">
      <header className="sidebar__header">
        {recipe.thumbnail_url && (
          <img className="sidebar__thumb" src={recipe.thumbnail_url} alt="" />
        )}
        <h1 className="sidebar__title">{recipe.title}</h1>
      </header>

      <section className="sidebar__section">
        <h2 className="sidebar__section-title">Ingrédients</h2>
        <ul className="ingredient-list">
          {recipe.ingredients.map((ing) => (
            <li key={ing.id} className="ingredient-list__item">
              <span>{ing.name}</span>
              {ing.quantity && <span className="ingredient-list__qty">{ing.quantity}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section className="sidebar__section">
        <h2 className="sidebar__section-title">Étapes</h2>
        <ol className="step-list">
          {recipe.steps.map((step, i) => {
            const isCurrent = cameraActive && i === currentStepIndex;
            const isDone = cameraActive && i < currentStepIndex;
            return (
              <li
                key={step.id}
                className={
                  "step-list__item" +
                  (isCurrent ? " step-list__item--current" : "") +
                  (isDone ? " step-list__item--done" : "")
                }
              >
                <span className="step-list__index">{i + 1}</span>
                <span className="step-list__text">{step.instruction}</span>
              </li>
            );
          })}
        </ol>
      </section>
    </aside>
  );
}
