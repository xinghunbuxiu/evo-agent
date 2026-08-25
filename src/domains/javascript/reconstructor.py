"""
JavaScript 项目重构器

将分析结果重构为可维护的项目结构
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from core import Experience, ExperienceStore


@dataclass
class ReconstructionPlan:
    """重构计划"""
    source_dir: Path
    target_dir: Path
    framework: str
    components: List[Dict[str, Any]]
    dependencies: List[str]
    pages: List[Dict[str, Any]]
    asset_manifest: Dict[str, Any]
    skill_template: Dict[str, Any]


class JSReconstructor:
    """JS 项目重构器"""
    
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
        self.exp_store = ExperienceStore(workspace, tenant_id)
    
    def create_plan(
        self,
        analysis_result: Dict[str, Any],
        source_dir: Path,
        skill_template: Optional[Dict[str, Any]] = None,
    ) -> ReconstructionPlan:
        """创建重构计划"""
        skill_template = skill_template if isinstance(skill_template, dict) else {}
        frameworks = analysis_result.get("frameworks", [])
        framework = str(skill_template.get("framework_hint") or "").strip().lower() or (frameworks[0] if frameworks else "unknown")
        
        components = []
        for lib in analysis_result.get("libraries", []):
            components.append({
                "name": lib["name"],
                "type": "library",
                "framework": lib.get("framework"),
            })

        inferred = self._infer_components(source_dir, framework)
        components.extend(inferred["components"])
        deduped_components: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in components:
            name = str(item.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            deduped_components.append(item)
        
        return ReconstructionPlan(
            source_dir=source_dir,
            target_dir=self._resolve_target_dir(skill_template),
            framework=framework,
            components=deduped_components,
            dependencies=[lib["name"] for lib in analysis_result.get("libraries", [])],
            pages=inferred["pages"],
            asset_manifest=inferred["asset_manifest"],
            skill_template=skill_template,
        )
    
    def execute_plan(
        self,
        plan: ReconstructionPlan,
        capability_id: str = "builtin.javascript",
        decision: Optional[Dict[str, Any]] = None,
        skill_template: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行重构计划"""
        skill_template = skill_template if isinstance(skill_template, dict) else {}
        # 创建目标目录
        plan.target_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成 package.json
        self._generate_package_json(plan)
        
        # 生成项目结构
        self._generate_project_structure(plan)
        
        # 记录经验
        exp = Experience(
            id=f"recon_{plan.framework}_{hash(plan.target_dir) % 10000}",
            domain="javascript",
            task_type="reconstruct",
            input_summary=str(plan.source_dir),
            output_summary=(
                f"Framework: {plan.framework}, Components: {len(plan.components)}, "
                f"Pages: {len(plan.pages)}, Routes: {len(plan.pages)}"
            ),
            quality_score=0.8,
            metadata={
                "capability_id": capability_id,
                "task_type": "reconstruct",
                "framework": plan.framework,
                "components_count": len(plan.components),
                "pages_count": len(plan.pages),
                "dependencies": plan.dependencies,
                "target_dir": str(plan.target_dir),
                "asset_manifest": plan.asset_manifest,
                "decision": decision or {},
                "skill_template": skill_template,
            }
        )
        self.exp_store.save(exp)
        
        return {
            "success": True,
            "target_dir": str(plan.target_dir),
            "framework": plan.framework,
            "components": len(plan.components),
            "skill_template_applied": bool(skill_template),
            "skill_template": skill_template,
        }

    def _resolve_target_dir(self, skill_template: Dict[str, Any]) -> Path:
        profile = skill_template.get("scaffold_profile", {}) if isinstance(skill_template.get("scaffold_profile"), dict) else {}
        suffix = str(profile.get("target_subdir") or skill_template.get("framework_hint") or "").strip().lower() or "default"
        return self.workspace / "reconstructed" / suffix
    
    def _generate_package_json(self, plan: ReconstructionPlan) -> None:
        """生成 package.json"""
        package = {
            "name": "reconstructed-project",
            "version": "1.0.0",
            "dependencies": {},
        }
        
        # 添加框架依赖
        if plan.framework == "vue":
            package["dependencies"]["vue"] = "^3.0.0"
            package["dependencies"]["vue-router"] = "^4.0.0"
        elif plan.framework == "react":
            package["dependencies"]["react"] = "^18.0.0"
            package["dependencies"]["react-dom"] = "^18.0.0"
            package["dependencies"]["react-router-dom"] = "^6.0.0"
        
        # 添加检测到的库
        for dep in plan.dependencies:
            package["dependencies"][dep] = "latest"
        
        # 保存
        with open(plan.target_dir / "package.json", "w") as f:
            json.dump(package, f, indent=2)
    
    def _generate_project_structure(self, plan: ReconstructionPlan) -> None:
        """生成项目结构"""
        # 创建标准目录
        for subdir in ["src", "src/components", "src/pages", "src/assets", "public", "config"]:
            (plan.target_dir / subdir).mkdir(exist_ok=True)

        self._copy_static_assets(plan)
        self._generate_route_manifest(plan)
        self._generate_asset_manifest(plan)
        self._generate_router_file(plan)
        self._generate_app_shell(plan)
        self._generate_readme(plan)

        entry_content = self._generate_entry_file(plan.framework)
        with open(plan.target_dir / "src" / "main.js", "w") as f:
            f.write(entry_content)

        for component in plan.components:
            self._generate_component_stub(plan, component)
    
    def _generate_entry_file(self, framework: str) -> str:
        """生成入口文件"""
        if framework == "vue":
            return '''import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

createApp(App).use(router).mount('#app')
'''
        elif framework == "react":
            return '''import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

const root = ReactDOM.createRoot(document.getElementById('root'))
root.render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
'''
        else:
            return '// Entry point\n'

    def _infer_components(self, source_dir: Path, framework: str) -> Dict[str, Any]:
        components: List[Dict[str, Any]] = []
        pages: List[Dict[str, Any]] = []
        asset_manifest: Dict[str, Any] = {"pages": {}, "shared": {"scripts": [], "styles": [], "preloads": []}}
        pages_dir = source_dir / "pages"
        if pages_dir.is_dir():
            for page_file in sorted(pages_dir.glob("*.html")):
                page_name = self._sanitize_component_name(page_file.stem)
                page_meta = self._extract_page_metadata(page_file)
                route_path = "/" if page_file.stem == "index" else f"/{page_file.stem}"
                pages.append({
                    "name": page_name,
                    "route_path": route_path,
                    "title": page_meta["title"],
                    "entry_script": page_meta["entry_script"],
                    "styles": page_meta["styles"],
                    "preloads": page_meta["preloads"],
                    "icon": page_meta["icon"],
                    "source": str(page_file),
                })
                asset_manifest["pages"][page_file.stem] = {
                    "route_path": route_path,
                    **page_meta,
                }
                components.append({
                    "name": page_name,
                    "type": "page",
                    "framework": framework,
                    "source": str(page_file),
                })

        assets_dir = source_dir / "assets"
        if assets_dir.is_dir():
            for asset_file in sorted(assets_dir.glob("*.js")):
                stem = asset_file.stem.split("-")[0]
                if stem in {"main", "naive", "_plugin", "index"}:
                    continue
                name = self._sanitize_component_name(stem)
                if not name or len(name) < 3:
                    continue
                inferred_type = "component" if any(token in name.lower() for token in ["dialog", "modal", "page"]) else "module"
                components.append({
                    "name": name,
                    "type": inferred_type,
                    "framework": framework,
                    "source": str(asset_file),
                })

        self._fill_shared_assets(asset_manifest)
        return {
            "components": components,
            "pages": pages,
            "asset_manifest": asset_manifest,
        }

    def _extract_page_metadata(self, page_file: Path) -> Dict[str, Any]:
        content = page_file.read_text(encoding="utf-8", errors="ignore")
        title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        script_match = re.search(r'<script[^>]+src="([^"]+)"', content, re.IGNORECASE)
        icon_match = re.search(r'<link[^>]+rel="icon"[^>]+href="([^"]+)"', content, re.IGNORECASE)
        stylesheet_matches = re.findall(
            r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"',
            content,
            re.IGNORECASE,
        )
        preload_matches = re.findall(
            r'<link[^>]+rel="modulepreload"[^>]+href="([^"]+)"',
            content,
            re.IGNORECASE,
        )
        return {
            "title": title_match.group(1).strip() if title_match else page_file.stem,
            "entry_script": script_match.group(1) if script_match else None,
            "styles": stylesheet_matches,
            "preloads": preload_matches,
            "icon": icon_match.group(1) if icon_match else None,
        }

    def _fill_shared_assets(self, asset_manifest: Dict[str, Any]) -> None:
        page_entries = list(asset_manifest.get("pages", {}).values())
        if not page_entries:
            return
        scripts = [item.get("entry_script") for item in page_entries if item.get("entry_script")]
        shared_scripts = sorted({item for item in scripts if scripts.count(item) > 1})
        styles = [style for item in page_entries for style in item.get("styles", [])]
        shared_styles = sorted({item for item in styles if styles.count(item) > 1})
        preloads = [preload for item in page_entries for preload in item.get("preloads", [])]
        shared_preloads = sorted({item for item in preloads if preloads.count(item) > 1})
        asset_manifest["shared"] = {
            "scripts": shared_scripts,
            "styles": shared_styles,
            "preloads": shared_preloads,
        }

    def _sanitize_component_name(self, value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9]+", " ", value).strip()
        if not normalized:
            return ""
        parts = [part[:1].upper() + part[1:] for part in normalized.split() if part]
        return "".join(parts)

    def _generate_component_stub(self, plan: ReconstructionPlan, component: Dict[str, Any]) -> None:
        name = str(component.get("name") or "").strip()
        if not name:
            return

        target_group = "pages" if component.get("type") == "page" else "components"
        page_meta = next((item for item in plan.pages if item.get("name") == name), None)
        if plan.framework == "react":
            file_path = plan.target_dir / "src" / target_group / f"{name}.jsx"
            if component.get("type") == "page":
                content = self._generate_react_page_stub(name, page_meta)
            else:
                content = self._generate_react_component_stub(name, component)
        elif plan.framework == "vue":
            file_path = plan.target_dir / "src" / target_group / f"{name}.vue"
            if component.get("type") == "page":
                content = self._generate_vue_page_stub(name, page_meta)
            else:
                content = (
                    "<template>\n"
                    f"  <div>{name} placeholder</div>\n"
                    "</template>\n\n"
                    "<script setup>\n"
                    "</script>\n"
                )
        else:
            file_path = plan.target_dir / "src" / target_group / f"{name}.js"
            content = f"export function {name}() {{\n  return '{name} placeholder'\n}}\n"

        file_path.write_text(content, encoding="utf-8")

    def _generate_react_page_stub(self, name: str, page_meta: Optional[Dict[str, Any]]) -> str:
        route_path = page_meta.get("route_path", "--") if isinstance(page_meta, dict) else "--"
        title = page_meta.get("title", name) if isinstance(page_meta, dict) else name
        entry_script = page_meta.get("entry_script", "--") if isinstance(page_meta, dict) else "--"
        styles = page_meta.get("styles", []) if isinstance(page_meta, dict) else []
        preloads = page_meta.get("preloads", []) if isinstance(page_meta, dict) else []
        source = page_meta.get("source", "--") if isinstance(page_meta, dict) else "--"
        return (
            f"export default function {name}() {{\n"
            "  return (\n"
            f"    <section data-route=\"{route_path}\" className=\"recovered-page\">\n"
            f"      <h1>{title}</h1>\n"
            "      <p>Recovered page scaffold ready for follow-up reverse engineering.</p>\n"
            "      <ul>\n"
            f"        <li>Route: {route_path}</li>\n"
            f"        <li>Original entry: {entry_script}</li>\n"
            f"        <li>Styles: {', '.join(styles) if styles else '--'}</li>\n"
            f"        <li>Preloads: {', '.join(preloads) if preloads else '--'}</li>\n"
            f"        <li>Source: {source}</li>\n"
            "      </ul>\n"
            "      <ol>\n"
            "        <li>Bind the real API calls and data contracts.</li>\n"
            "        <li>Replace placeholder layout with recovered UI blocks.</li>\n"
            "        <li>Verify navigation, auth guard, and asset loading.</li>\n"
            "      </ol>\n"
            "    </section>\n"
            "  )\n"
            "}\n"
        )

    def _generate_react_component_stub(self, name: str, component: Dict[str, Any]) -> str:
        source = component.get("source") or "--"
        component_type = component.get("type") or "component"
        return (
            f"export default function {name}() {{\n"
            "  return (\n"
            "    <section className=\"recovered-component\">\n"
            f"      <h2>{name}</h2>\n"
            f"      <p>Recovered {component_type} placeholder.</p>\n"
            "      <ul>\n"
            f"        <li>Source: {source}</li>\n"
            f"        <li>Recovery type: {component_type}</li>\n"
            "      </ul>\n"
            "    </section>\n"
            "  )\n"
            "}\n"
        )

    def _generate_vue_page_stub(self, name: str, page_meta: Optional[Dict[str, Any]]) -> str:
        route_path = page_meta.get("route_path", "--") if isinstance(page_meta, dict) else "--"
        title = page_meta.get("title", name) if isinstance(page_meta, dict) else name
        entry_script = page_meta.get("entry_script", "--") if isinstance(page_meta, dict) else "--"
        styles = page_meta.get("styles", []) if isinstance(page_meta, dict) else []
        preloads = page_meta.get("preloads", []) if isinstance(page_meta, dict) else []
        return (
            "<template>\n"
            f"  <section data-route=\"{route_path}\" class=\"recovered-page\">\n"
            f"    <h1>{title}</h1>\n"
            f"    <p>Recovered page scaffold for {name}.</p>\n"
            f"    <p>Original entry: {entry_script}</p>\n"
            f"    <p>Styles: {', '.join(styles) if styles else '--'}</p>\n"
            f"    <p>Preloads: {', '.join(preloads) if preloads else '--'}</p>\n"
            "  </section>\n"
            "</template>\n\n"
            "<script setup>\n"
            "</script>\n"
        )

    def _generate_route_manifest(self, plan: ReconstructionPlan) -> None:
        payload = {
            "framework": plan.framework,
            "skill_template": plan.skill_template,
            "routes": [
                {
                    "name": page.get("name"),
                    "path": page.get("route_path"),
                    "title": page.get("title"),
                    "entry_script": page.get("entry_script"),
                    "styles": page.get("styles", []),
                    "preloads": page.get("preloads", []),
                    "source": page.get("source"),
                    "recovery_notes": [
                        "bind real data flow",
                        "verify route guard and auth state",
                        "compare rendered blocks with original page",
                    ],
                }
                for page in plan.pages
            ],
        }
        (plan.target_dir / "src" / "routes.generated.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _generate_asset_manifest(self, plan: ReconstructionPlan) -> None:
        (plan.target_dir / "config" / "asset-manifest.json").write_text(
            json.dumps(plan.asset_manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _generate_router_file(self, plan: ReconstructionPlan) -> None:
        if plan.framework == "react":
            imports = []
            route_defs = []
            for page in plan.pages:
                imports.append(f"import {page['name']} from './pages/{page['name']}'")
                route_defs.append(
                    "  {\n"
                    f"    path: '{page['route_path']}',\n"
                    f"    name: '{page['name']}',\n"
                    f"    title: {json.dumps(page.get('title') or page['name'], ensure_ascii=False)},\n"
                    f"    Component: {page['name']},\n"
                    "  }"
                )
            content = "\n".join(imports) + "\n\n" + "export const routes = [\n" + ",\n".join(route_defs) + "\n]\n"
        elif plan.framework == "vue":
            imports = ["import { createRouter, createWebHistory } from 'vue-router'"]
            page_imports = []
            route_defs = []
            for page in plan.pages:
                page_imports.append(f"import {page['name']} from './pages/{page['name']}.vue'")
                route_defs.append(
                    "  {\n"
                    f"    path: '{page['route_path']}',\n"
                    f"    name: '{page['name']}',\n"
                    f"    component: {page['name']},\n"
                    "  }"
                )
            content = (
                "\n".join(imports + page_imports)
                + "\n\nconst routes = [\n"
                + ",\n".join(route_defs)
                + "\n]\n\nexport default createRouter({\n  history: createWebHistory(),\n  routes,\n})\n"
            )
        else:
            content = "export const routes = []\n"
        (plan.target_dir / "src" / "router.js").write_text(content, encoding="utf-8")

    def _generate_app_shell(self, plan: ReconstructionPlan) -> None:
        if plan.framework == "react":
            skill_name = plan.skill_template.get("skill_name") if isinstance(plan.skill_template, dict) else None
            content = (
                "import { Link, Route, Routes } from 'react-router-dom'\n"
                "import { routes } from './router'\n\n"
                "export default function App() {\n"
                "  return (\n"
                "    <div className=\"reconstructed-app\">\n"
                f"      <header><h1>Recovered {plan.framework.title()} App</h1><p>Template: {skill_name or 'default scaffold'}</p></header>\n"
                "      <nav>\n"
                "        {routes.map((route) => (\n"
                "          <Link key={route.path} to={route.path} style={{ marginRight: 12 }}>\n"
                "            {route.title || route.name}\n"
                "          </Link>\n"
                "        ))}\n"
                "      </nav>\n"
                "      <main>\n"
                "        <Routes>\n"
                "          {routes.map((route) => (\n"
                "            <Route key={route.path} path={route.path} element={<route.Component />} />\n"
                "          ))}\n"
                "        </Routes>\n"
                "      </main>\n"
                "    </div>\n"
                "  )\n"
                "}\n"
            )
            (plan.target_dir / "src" / "App.jsx").write_text(content, encoding="utf-8")
        elif plan.framework == "vue":
            nav_links = "\n".join(
                [
                    f'      <RouterLink to="{page["route_path"]}">{page.get("title") or page["name"]}</RouterLink>'
                    for page in plan.pages
                ]
            )
            content = (
                "<template>\n"
                "  <div class=\"reconstructed-app\">\n"
                "    <nav class=\"route-nav\">\n"
                f"{nav_links}\n"
                "    </nav>\n"
                "    <main>\n"
                "      <RouterView />\n"
                "    </main>\n"
                "  </div>\n"
                "</template>\n\n"
                "<script setup>\n"
                "import { RouterLink, RouterView } from 'vue-router'\n"
                "</script>\n"
            )
            (plan.target_dir / "src" / "App.vue").write_text(content, encoding="utf-8")

    def _generate_readme(self, plan: ReconstructionPlan) -> None:
        accepted = plan.skill_template.get("accepted_tasks", []) if isinstance(plan.skill_template, dict) else []
        acceptance = plan.skill_template.get("acceptance", {}) if isinstance(plan.skill_template, dict) and isinstance(plan.skill_template.get("acceptance"), dict) else {}
        content = (
            "# Reconstructed Project\n\n"
            f"- Framework: `{plan.framework}`\n"
            f"- Source directory: `{plan.source_dir}`\n"
            f"- Target directory: `{plan.target_dir}`\n"
            f"- Skill template: `{plan.skill_template.get('skill_name') or 'default scaffold'}`\n"
            f"- Accepted tasks: `{', '.join(accepted) if accepted else '--'}`\n"
            f"- Acceptance baseline: verdict=`{acceptance.get('evaluation_verdict') or '--'}`, "
            f"components_min=`{acceptance.get('components_min') or '--'}`, "
            f"has_target_dir=`{acceptance.get('has_target_dir')}`\n\n"
            "## Recovery Checklist\n\n"
            "1. Compare generated routes with original page HTML and entry scripts.\n"
            "2. Replace placeholder components with recovered UI and state flows.\n"
            "3. Wire APIs, auth logic, and external assets.\n"
            "4. Re-run mission validation after each major restoration step.\n"
        )
        (plan.target_dir / "README.md").write_text(content, encoding="utf-8")

    def _copy_static_assets(self, plan: ReconstructionPlan) -> None:
        raw_assets = plan.source_dir / "assets"
        logo_candidates = [raw_assets / "logo.svg", plan.source_dir / "logo.svg"]
        for candidate in logo_candidates:
            if candidate.is_file():
                shutil.copyfile(candidate, plan.target_dir / "src" / "assets" / candidate.name)
                break
