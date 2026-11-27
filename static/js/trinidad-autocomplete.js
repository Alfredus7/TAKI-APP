(function (global) {
    'use strict';

    const TRINIDAD_LAT = -14.8348;
    const TRINIDAD_LNG = -64.9042;
    const TRINIDAD_BBOX = '-64.98,-14.91,-64.82,-14.76';
    const TRINIDAD_VIEWBOX = '-64.98,-14.76,-64.82,-14.91';
    const RECENT_KEY = 'teki_ubicaciones_trinidad_v2';

    const ICONO_RELOJ = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/>
        </svg>`;

    const ICONO_PIN = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
        </svg>`;

    function getRecientes() {
        try {
            return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
        } catch {
            return [];
        }
    }

    function guardarReciente(item) {
        const actuales = getRecientes().filter((x) => x.titulo !== item.titulo);
        actuales.unshift(item);
        localStorage.setItem(RECENT_KEY, JSON.stringify(actuales.slice(0, 5)));
    }

    function normalizar(texto) {
        return (texto || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    async function consultarNominatim(q) {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q + ', Trinidad, Beni, Bolivia')}&countrycodes=bo&viewbox=${TRINIDAD_VIEWBOX}&limit=6&addressdetails=1`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'es' } });
        if (!res.ok) return [];
        const data = await res.json();

        return (data || [])
            .map((place) => {
                const partes = (place.display_name || '').split(',').map((s) => s.trim()).filter(Boolean);
                const titulo = partes[0] || 'Ubicación';
                const detalle = partes.slice(1, 3).join(', ') || 'Trinidad';
                return {
                    titulo,
                    detalle,
                    lat: parseFloat(place.lat),
                    lng: parseFloat(place.lon)
                };
            })
            .filter((x) => !Number.isNaN(x.lat) && !Number.isNaN(x.lng));
    }

    async function consultarPhoton(q) {
        const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(q)}&lat=${TRINIDAD_LAT}&lon=${TRINIDAD_LNG}&bbox=${TRINIDAD_BBOX}&limit=6&lang=es`;
        const res = await fetch(url);
        if (!res.ok) return [];
        const data = await res.json();

        return (data.features || [])
            .map((feat) => {
                const p = feat.properties || {};
                const [lng, lat] = feat.geometry.coordinates;
                const titulo = p.name || p.street || 'Ubicación';
                const partesDetalle = [p.street, p.district, 'Trinidad'].filter(Boolean);
                const detalle = partesDetalle.filter((d) => normalizar(d) !== normalizar(titulo)).join(', ') || 'Trinidad';
                return { titulo, detalle, lat, lng };
            })
            .filter((x) => !Number.isNaN(x.lat) && !Number.isNaN(x.lng));
    }

    function resolveEl(ref) {
        if (!ref) return null;
        return typeof ref === 'string' ? document.getElementById(ref) : ref;
    }

    function attach(config) {
        const input = resolveEl(config.input);
        const dropdown = resolveEl(config.dropdown);
        const box = resolveEl(config.box);
        const btnLimpiar = resolveEl(config.btnLimpiar);
        const btnBuscar = resolveEl(config.btnBuscar);
        const latInput = resolveEl(config.latInput);
        const lngInput = resolveEl(config.lngInput);
        const soloTitulo = Boolean(config.soloTitulo);
        const onSelect = config.onSelect || null;

        if (!input || !dropdown || input.dataset.tekiAutocompleteBound === '1') return;
        input.dataset.tekiAutocompleteBound = '1';

        function renderItems(items, esReciente = false) {
            dropdown.innerHTML = '';
            if (!items.length) {
                dropdown.style.display = 'none';
                return;
            }

            items.forEach((item) => {
                const li = document.createElement('li');
                li.className = 'gmaps-item';
                li.innerHTML = `
                    <span class="gmaps-item-icon">${esReciente ? ICONO_RELOJ : ICONO_PIN}</span>
                    <span class="gmaps-item-text">
                        <span class="gmaps-lugar-nombre">${item.titulo}</span>
                        <span class="gmaps-lugar-detalle">${item.detalle}</span>
                    </span>
                `;
                li.addEventListener('click', () => {
                    const textoCompleto = item.detalle ? `${item.titulo}, ${item.detalle}` : item.titulo;
                    const textoFinal = soloTitulo ? item.titulo : textoCompleto;
                    const latFmt = Number(item.lat).toFixed(6);
                    const lngFmt = Number(item.lng).toFixed(6);

                    input.value = textoFinal;
                    if (latInput) latInput.value = latFmt;
                    if (lngInput) lngInput.value = lngFmt;
                    if (btnLimpiar) btnLimpiar.style.display = 'inline-flex';
                    dropdown.style.display = 'none';
                    guardarReciente({ ...item, detalle: item.detalle || 'Trinidad' });

                    if (typeof onSelect === 'function') {
                        onSelect({ ...item, texto: textoFinal, textoCompleto, lat: latFmt, lng: lngFmt });
                    }
                });
                dropdown.appendChild(li);
            });

            dropdown.style.display = 'block';
        }

        async function buscarEnAPI(query) {
            const q = query.trim();
            if (!q) {
                renderItems(getRecientes(), true);
                return;
            }
            if (q.length < 2) {
                dropdown.style.display = 'none';
                return;
            }

            try {
                const [resNominatim, resPhoton] = await Promise.allSettled([
                    consultarNominatim(q),
                    consultarPhoton(q)
                ]);

                const combinados = [];
                const agregar = (lista) => {
                    lista.forEach((item) => {
                        const existe = combinados.some(
                            (c) => normalizar(c.titulo) === normalizar(item.titulo) &&
                                   normalizar(c.detalle) === normalizar(item.detalle)
                        );
                        if (!existe) combinados.push(item);
                    });
                };

                if (resNominatim.status === 'fulfilled') agregar(resNominatim.value);
                if (resPhoton.status === 'fulfilled') agregar(resPhoton.value);

                renderItems(combinados.slice(0, 7), false);
            } catch {
                dropdown.style.display = 'none';
            }
        }

        let debounceTimer = null;

        input.addEventListener('focus', () => {
            if (!input.value.trim()) {
                renderItems(getRecientes(), true);
            } else if (!latInput || !latInput.value) {
                buscarEnAPI(input.value);
            }
        });

        input.addEventListener('input', () => {
            if (latInput) latInput.value = '';
            if (lngInput) lngInput.value = '';
            if (btnLimpiar) btnLimpiar.style.display = input.value.length ? 'inline-flex' : 'none';

            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => buscarEnAPI(input.value), 280);
        });

        if (btnLimpiar) {
            btnLimpiar.addEventListener('click', () => {
                input.value = '';
                if (latInput) latInput.value = '';
                if (lngInput) lngInput.value = '';
                btnLimpiar.style.display = 'none';
                input.focus();
                renderItems(getRecientes(), true);
            });
        }

        if (btnBuscar) {
            btnBuscar.addEventListener('click', () => {
                buscarEnAPI(input.value);
            });
        }

        document.addEventListener('click', (e) => {
            const dentroCaja = box && box.id ? e.target.closest('#' + box.id) : false;
            const dentroLista = dropdown.id ? e.target.closest('#' + dropdown.id) : false;
            if (!dentroCaja && !dentroLista) {
                dropdown.style.display = 'none';
            }
        });

        if (btnLimpiar && input.value.trim()) {
            btnLimpiar.style.display = 'inline-flex';
        }
    }

    function initAll() {
        document.querySelectorAll('[data-trinidad-autocomplete]').forEach((input) => {
            const prefix = input.dataset.prefix || input.id;
            attach({
                input,
                box: input.dataset.box || `caja-buscador-${prefix}`,
                dropdown: input.dataset.dropdown || `sugerencias-${prefix}`,
                btnLimpiar: input.dataset.limpiar || `btn-limpiar-${prefix}`,
                btnBuscar: input.dataset.buscar || `btn-buscar-${prefix}`,
                latInput: input.dataset.lat || `${prefix}_lat`,
                lngInput: input.dataset.lng || `${prefix}_lng`,
                soloTitulo: input.dataset.soloTitulo === 'true'
            });
        });
    }

    global.TekiAutocomplete = { attach, initAll };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})(window);