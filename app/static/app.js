// Eigener JavaScript-Code (SPEC.md Abschnitt 4). Gespeichert wird nur, was der
// Server prüft und rechnet; hier wird lediglich vorab angezeigt.

// Wie _zaehlerstand() in main.py: Ein Punkt vor genau drei Ziffern ist ein
// Tausenderpunkt (150.637 km), sonst Komma oder Punkt als Dezimalzeichen.
function zaehlerstand(text) {
  const t = text.trim().replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
  return t === "" || isNaN(t) ? null : Number(t);
}

function zahlDe(wert) {
  return wert.toLocaleString("de-DE", { maximumFractionDigits: 1 });
}

document.addEventListener("alpine:init", () => {
  // Fuhrpark → Erfassen: Tankfelder nur bei „Tanken“, Liter und Warnungen sofort.
  Alpine.data("erfassen", () => ({
    fahrzeug: {},  // tank, stand, einheit; setzt der nachgeladene Fahrzeug-Block
    art: "",
    stand: "",
    prozent: "90",
    liter: "",
    beleg: "",
    bemerkung: "",

    // Von „erledigen“ an einer Fälligkeit vorbelegt; x-model würde den Wert sonst leeren.
    init() {
      this.art = this.$el.dataset.art || "";
    },

    get tanken() {
      return this.art.trim().toLowerCase() === "tanken";
    },

    get literText() {
      if (this.liter.trim()) return "";
      const tank = Number(this.fahrzeug.tank);
      if (!tank) return "Für dieses Fahrzeug ist keine Tankgröße hinterlegt – bitte die genauen Liter eintragen.";
      return `${this.prozent} % = ${zahlDe(Math.round(tank * this.prozent / 10) / 10)} L`;
    },

    get standWarnung() {
      const neu = zaehlerstand(this.stand);
      const letzter = this.fahrzeug.stand ? Number(this.fahrzeug.stand) : null;
      if (neu === null || letzter === null || neu >= letzter) return "";
      return `Kleiner als der letzte Stand (${zahlDe(letzter)} ${this.fahrzeug.einheit}). Zähler getauscht oder Tippfehler?`;
    },

    // Nach dem Speichern bleiben Fahrzeug und Datum stehen, für den nächsten Eintrag.
    leeren() {
      Object.assign(this, { art: "", stand: "", prozent: "90", liter: "", beleg: "", bemerkung: "" });
    },
  }));
});
