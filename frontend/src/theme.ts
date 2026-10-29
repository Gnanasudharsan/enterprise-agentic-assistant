import { useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";

const KEY = "eaa.theme";

function read(): ThemePreference {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Theme preference, persisted per browser. "system" follows the OS setting. */
export function useTheme(): [ThemePreference, (t: ThemePreference) => void] {
  const [theme, setTheme] = useState<ThemePreference>(read);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, theme);
    } catch {
      // Storage unavailable; the choice still applies for this session.
    }
  }, [theme]);

  return [theme, setTheme];
}
