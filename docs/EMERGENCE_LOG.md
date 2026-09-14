# Registro de emergencia

Todo comportamiento que no fue programado explícitamente y sorprendió, con semilla y turno para
reproducirlo. Es la materia prima del portfolio y de los evals de realismo político.

| Fecha | Versión | Semilla | Turno | Qué pasó | Por qué es interesante | Reproducir |
|---|---|---|---|---|---|---|
| 2026-09 | v0.1 | varias | 20–48 | Trampa de inflación crónica: shocks agotan reservas, cae la confianza institucional y la inflación queda en 5–14 % mensual con aprobación 0 sin llegar a hiperinflación. El BC pasivo no sale solo. | Estado absorbente coherente que no estaba diseñado; obliga al jugador a actuar. | `republica batch --seeds 300 --policy passive` y mirar las corridas con aprobación final < 5 |
| 2026-09 | v0.2 | 7 | 13–48 | Un gobierno que ajusta siempre (opción A en todos los dilemas) con tasa nominal fija termina en deflación, desempleo 16 % y aprobación 19. | Sobreajuste castigado sin que nadie lo programara: emerge de tasa real alta + indexación salarial. | `republica play --seed 7 --auto` |
