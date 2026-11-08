/* ================================================================
   INTEGRAÇÃO API — Agente Digital Tech
   Cole este script NO FINAL do <body> do seu index.html, depois do
   <script> principal (ele sobrescreve algumas funções do painel).
   ================================================================ */

// Mesma origem por padrão (útil se o FastAPI também servir o /static).
// Se a API rodar separada durante o desenvolvimento, troque para
// 'http://localhost:8000' (sem barra no final).
const API_BASE = 'http://localhost:8000';

// ------------------------------------------------------------------
// Helpers HTTP
// ------------------------------------------------------------------
async function apiGet(path) {
    const r = await fetch(API_BASE + path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiPost(path, body = {}) {
    const r = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiPatch(path, body = {}) {
    const r = await fetch(API_BASE + path, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiDelete(path) {
    const r = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}

// ------------------------------------------------------------------
// 1. SUBSTITUIÇÃO: carregamento inicial do state
// ------------------------------------------------------------------
async function loadStateFromAPI() {
    try {
        // Carrega todos os conteúdos (artigos + notícias)
        state.items = await apiGet('/api/conteudos');

        // /api/categorias devolve objetos completos {id,nome,slug,parent_id}
        // (útil para outras telas) -- mas os <select> do painel esperam uma
        // lista simples de strings. Extraímos o nome aqui.
        const categoriasApi = await apiGet('/api/categorias');
        state.categories = categoriasApi.map(c => c.nome).filter(Boolean);

        // Atualiza dashboard
        await refreshDashboard();
        // Renderiza página atual
        renderPage(state.currentPage || 'dashboard');
        showToast('Dados sincronizados com o servidor.', 'success');
    } catch (e) {
        console.error(e);
        showToast('Erro ao sincronizar com API: ' + e.message, 'error');
    }
}

// ------------------------------------------------------------------
// 2. Dashboard: NÃO sobrescrevemos renderDashboard() aqui de propósito.
//    A função original (em index.html) já lê os contadores direto de
//    state.items, que loadStateFromAPI() preenche com dados reais da API
//    -- então Artigos/Notícias/Em revisão/Publicados já saem corretos
//    sozinhos, sem precisar duplicar o template e sem risco de truncar
//    seções (Hub de Atalhos, atividade recente etc.) por engano.
//    state.dashboard fica disponível caso você queira usar as contagens
//    vindas de /api/dashboard em algum lugar específico no futuro.
// ------------------------------------------------------------------
async function refreshDashboard() {
    try {
        const stats = await apiGet('/api/dashboard');
        state.dashboard = stats;
    } catch (e) {
        console.warn('Dashboard stats não disponíveis', e);
    }
}

// ------------------------------------------------------------------
// 3. SUBSTITUIÇÃO: listagem com filtros via API
// ------------------------------------------------------------------
window.filterLibrary = async function(type) {
    const label = type === 'artigos' ? 'artigo' : 'noticia';
    const q = (document.getElementById('library-search')?.value || '').toLowerCase();
    const status = document.getElementById('library-status-filter')?.value || '';
    const cat = document.getElementById('library-category-filter')?.value || '';
    const tag = (document.getElementById('library-tag-filter')?.value || '').toLowerCase();
    const sort = document.getElementById('library-sort-filter')?.value || 'recent';

    try {
        const params = new URLSearchParams();
        params.set('tipo', label);
        if (status) params.set('status', status);
        if (cat) params.set('categoria', cat);
        if (tag) params.set('tag', tag);
        if (q) params.set('search', q);
        params.set('sort', sort);

        const filtered = await apiGet(`/api/conteudos?${params.toString()}`);
        const table = document.getElementById('library-table');
        if (table) table.innerHTML = filtered.length ? renderRows(filtered)
            : '<div class="empty-state">Nenhum conteúdo corresponde aos filtros atuais.</div>';
        const count = document.getElementById('library-count');
        if (count) count.textContent = filtered.length + ' itens';
    } catch (e) {
        showToast('Erro ao filtrar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 4. SUBSTITUIÇÃO: salvar conteúdo (criar ou editar)
//    Agora aceita (publish, statusOverride) -- os botões do formulário
//    chamam saveContent(false), saveContent(true,'revisao') e
//    saveContent(true,'publicado'); antes esses argumentos eram
//    ignorados e os três botões faziam a mesma coisa (usavam sempre o
//    valor do <select> de status).
// ------------------------------------------------------------------
window.saveContent = async function(publish, statusOverride) {
    const get = id => document.getElementById(id)?.value;
    const payload = {
        titulo: (get('form-titulo') || '').trim(),
        resumo: (get('form-resumo') || '').trim(),
        conteudo: get('form-conteudo') || '',
        categoria: get('form-categoria') || '',
        tags: (get('form-tags') || '').split(',').map(t => t.trim()).filter(Boolean),
        status: statusOverride || get('form-status') || 'rascunho',
        tipo: (state.editingType === 'notícia' || state.activeForm === 'notícia') ? 'noticia' : 'artigo',
        imagem_url: (get('form-featured-url') || '').trim() || null,
        seo_title: (get('seo-title') || '').trim() || null,
        seo_description: (get('seo-description') || '').trim() || null,
        slug: (get('form-slug') || '').trim() || null,
    };

    if (!payload.titulo) {
        showToast('O título é obrigatório.', 'warning');
        return;
    }

    try {
        if (state.editingId) {
            await apiPatch(`/api/conteudos/${state.editingId}`, payload);
            showToast('Conteúdo atualizado com sucesso!', 'success');
        } else {
            await apiPost('/api/conteudos', payload);
            showToast('Conteúdo criado com sucesso!', 'success');
        }
        const tipoAlvo = payload.tipo;
        state.editingId = null;
        await loadStateFromAPI();
        navigateTo(tipoAlvo === 'noticia' ? 'noticias' : 'artigos');
    } catch (e) {
        showToast('Erro ao salvar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 5. SUBSTITUIÇÃO: excluir item
// ------------------------------------------------------------------
window.deleteItem = async function(id) {
    if (!confirm('Tem certeza que deseja excluir este conteúdo?')) return;
    try {
        await apiDelete(`/api/conteudos/${id}`);
        showToast('Conteúdo excluído.', 'success');
        await loadStateFromAPI();
        renderPage(state.currentPage);
    } catch (e) {
        showToast('Erro ao excluir: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 6. SUBSTITUIÇÃO: editar item (carrega do servidor)
//    Corrigido: antes os set() rodavam ANTES de navigateTo(), ou seja,
//    antes do formulário existir no DOM -- eram um no-op. Agora
//    navegamos primeiro (o que renderiza o formulário) e só depois
//    preenchemos os campos que o renderForm() do index.html não sabe
//    montar sozinho a partir do item vindo da API (conteudo completo,
//    imagem, SEO). Também disparamos os updates de preview, que antes
//    nunca eram chamados aqui.
// ------------------------------------------------------------------
window.editItem = async function(id) {
    try {
        const item = await apiGet(`/api/conteudos/${id}`);
        state.editingId = item.id;
        state.editingType = item.tipo === 'noticia' ? 'notícia' : 'artigo';

        navigateTo(state.editingType === 'notícia' ? 'publicar-noticia' : 'publicar');

        const set = (elId, val) => { const el = document.getElementById(elId); if (el) el.value = val || ''; };
        set('form-titulo', item.titulo);
        set('form-resumo', item.resumo);
        set('form-conteudo', item.conteudo);
        set('form-categoria', item.categoria);
        set('form-tags', (item.tags || []).join(', '));
        set('form-status', item.status);
        set('form-slug', item.slug);
        set('form-featured-url', item.imagem_url);
        set('seo-title', item.seo_title);
        set('seo-description', item.seo_description);

        // O form-slug já veio preenchido: marca como "manual" para o
        // syncSlug() do index.html não sobrescrevê-lo ao focar o título.
        const slugField = document.getElementById('form-slug');
        if (slugField && item.slug) slugField.dataset.manual = '1';

        if (typeof updatePreview === 'function') updatePreview();
        if (typeof previewFeatured === 'function') previewFeatured();
        if (typeof updateSEOPreview === 'function') updateSEOPreview();
        if (typeof updateLivePublicationPreview === 'function') updateLivePublicationPreview();
    } catch (e) {
        showToast('Erro ao carregar edição: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 7. SUBSTITUIÇÃO: gerar artigo com IA
//    ATENÇÃO: /api/artigos/gerar ainda não existe no api.py (fase
//    seguinte, roteado para pipeline/gerar_artigos.py). Até lá este
//    botão específico vai mostrar um toast de erro -- o resto do
//    painel (listar/criar/editar/excluir/publicar) não depende disso.
// ------------------------------------------------------------------
window.gerarArtigo = async function() {
    const tema = document.getElementById('artigo-tema')?.value.trim();
    if (!tema) { showToast('Informe o tema do artigo.', 'warning'); return; }
    showToast('Gerando artigo com IA...', 'info');
    try {
        await apiPost('/api/artigos/gerar', {
            tema,
            categoria: document.getElementById('artigo-categoria')?.value || 'Tecnologia',
            tom: document.getElementById('artigo-tom')?.value,
            tamanho: document.getElementById('artigo-tamanho')?.value,
            publicar_imediatamente: document.getElementById('artigo-publicar')?.checked ?? false
        });
        showToast('Artigo gerado e enviado para revisão!', 'success');
        await loadStateFromAPI();
        navigateTo('artigos');
    } catch (e) {
        showToast('Geração com IA ainda não disponível no backend: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 8. SUBSTITUIÇÃO: gerar notícia com IA
//    Mesma ressalva: /api/noticias/gerar ainda não existe no api.py.
// ------------------------------------------------------------------
window.gerarNoticia = async function() {
    const tema = document.getElementById('noticia-tema')?.value.trim();
    showToast('Gerando notícia com IA...', 'info');
    try {
        await apiPost('/api/noticias/gerar', {
            tema: tema || null,
            categoria: document.getElementById('noticia-categoria')?.value || 'Tecnologia',
            publicar_imediatamente: document.getElementById('noticia-publicar')?.checked ?? false
        });
        showToast('Notícia gerada e enviada para revisão!', 'success');
        await loadStateFromAPI();
        navigateTo('noticias');
    } catch (e) {
        showToast('Geração com IA ainda não disponível no backend: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 9. SUBSTITUIÇÃO: publicar conteúdo
// ------------------------------------------------------------------
window.publicarItem = async function(id) {
    try {
        await apiPost(`/api/conteudos/${id}/publicar`);
        showToast('Conteúdo publicado com sucesso!', 'success');
        await loadStateFromAPI();
        renderPage(state.currentPage);
    } catch (e) {
        showToast('Erro ao publicar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 10. SUBSTITUIÇÃO: health check real
// ------------------------------------------------------------------
window.checkHealthReal = async function() {
    try {
        const h = await apiGet('/api/health');
        updateAgentStatus(
            h.banco === 'ok' ? 'success' : 'error',
            `API: ${h.api} | Banco: ${h.banco} | IA: ${h.ia}`
        );
    } catch (e) {
        updateAgentStatus('error', 'API indisponível');
    }
};

// ------------------------------------------------------------------
// 11. INICIALIZAÇÃO: troca o load inicial (mockado) pelo real
// ------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', async () => {
    await loadStateFromAPI();
    setInterval(checkHealthReal, 30000);
    checkHealthReal();
});