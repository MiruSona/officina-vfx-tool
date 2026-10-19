using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Officina.Vfx.Editor
{
    // 모듈 하나 = 정적 함수 하나 (main · emission · shape · renderer). 수명 모듈 여섯은 VfxLifetimeModules.
    // 모르는 칸 · 값은 예외가 아니라 result issue 로 남긴다.
    public static class VfxModules
    {
        private static readonly List<ParticleSystemVertexStream> SnapStreams = new List<ParticleSystemVertexStream>
        {
            ParticleSystemVertexStream.Position,
            ParticleSystemVertexStream.Color,
            ParticleSystemVertexStream.UV,
            ParticleSystemVertexStream.Center,
        };

        public static void ReportExtra(VfxResult result, string layer, string prefix, IDictionary<string, JToken> extra)
        {
            if (extra == null) { return; }
            foreach (string key in extra.Keys)
            {
                result.Issue("build.unknown_field", layer, prefix + key);
            }
        }

        // main 은 끌 수 없는 모듈이라 늘 duration · loop · space 를 넣는다. 멈춘 상태에서 불러야 한다.
        public static void ApplyMain(ParticleSystem ps, VfxRecipe recipe, VfxLayer layer, VfxResult result)
        {
            var main = ps.main;
            main.duration = recipe.Duration;
            main.loop = recipe.Loop;
            main.playOnAwake = true;
            main.simulationSpace = ParseSpace(layer.Space, layer.Name, "space", result);

            VfxMainModule m = layer.Main;
            if (m == null) { return; }
            ReportExtra(result, layer.Name, "main.", m.Extra);
            if (m.StartDelay != null) { main.startDelay = m.StartDelay.ToMinMaxCurve(); }
            if (m.StartLifetime != null) { main.startLifetime = m.StartLifetime.ToMinMaxCurve(); }
            if (m.StartSpeed != null) { main.startSpeed = m.StartSpeed.ToMinMaxCurve(); }
            if (m.StartSize != null) { main.startSize = m.StartSize.ToMinMaxCurve(); }
            if (m.StartColor != null) { main.startColor = m.StartColor.ToMinMaxGradient(); }
            if (m.GravityModifier != null) { main.gravityModifier = m.GravityModifier.ToMinMaxCurve(); }
            if (m.MaxParticles.HasValue) { main.maxParticles = m.MaxParticles.Value; }
            if (m.StartRotation != null) { main.startRotation = m.StartRotation.ToMinMaxCurve(); }
        }

        public static void ApplyEmission(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var emission = ps.emission;
            VfxEmissionModule m = layer.Emission;
            emission.enabled = m != null;
            if (m == null) { return; }
            ReportExtra(result, layer.Name, "emission.", m.Extra);

            emission.rateOverTime = new ParticleSystem.MinMaxCurve(0f);
            if (m.RateOverTime != null) { emission.rateOverTime = m.RateOverTime.ToMinMaxCurve(); }

            var bursts = new List<ParticleSystem.Burst>();
            if (m.Bursts != null)
            {
                foreach (VfxBurst burst in m.Bursts)
                {
                    bursts.Add(burst.ToBurst());
                }
            }
            emission.SetBursts(bursts.ToArray());
        }

        public static void ApplyShape(ParticleSystem ps, VfxLayer layer, VfxResult result)
        {
            var shape = ps.shape;
            VfxShapeModule m = layer.Shape;
            shape.enabled = m != null;
            if (m == null) { return; }
            ReportExtra(result, layer.Name, "shape.", m.Extra);

            if (m.Type != null)
            {
                if (TryParseShape(m.Type, out ParticleSystemShapeType type)) { shape.shapeType = type; }
                else { result.Issue("build.bad_value", layer.Name, $"shape.type={m.Type}"); }
            }
            if (m.Radius.HasValue) { shape.radius = m.Radius.Value; }
            if (m.Angle.HasValue) { shape.angle = m.Angle.Value; }
            if (m.Arc.HasValue) { shape.arc = m.Arc.Value; }
            if (m.RadiusThickness.HasValue) { shape.radiusThickness = m.RadiusThickness.Value; }
            if (m.Box != null) { shape.scale = ToVector3(m.Box, 1f); }
            if (m.Position != null) { shape.position = ToVector3(m.Position, 0f); }
            if (m.Rotation != null) { shape.rotation = ToVector3(m.Rotation, 0f); }
        }

        // Billboard · 스냅 셰이더 짝 정점 스트림(Position · Color · UV · Center) · 정렬 · 머티리얼.
        public static void ApplyRenderer(ParticleSystem ps, VfxRecipe recipe, VfxLayer layer, Material material, VfxResult result)
        {
            var renderer = ps.GetComponent<ParticleSystemRenderer>();
            VfxRendererModule m = layer.Renderer;
            if (m != null)
            {
                ReportExtra(result, layer.Name, "renderer.", m.Extra);
                if (m.RenderMode != null && m.RenderMode != "Billboard")
                {
                    result.Issue("build.bad_value", layer.Name, $"renderer.renderMode={m.RenderMode} — Billboard 로 둠");
                }
            }

            renderer.renderMode = ParticleSystemRenderMode.Billboard;
            renderer.SetActiveVertexStreams(SnapStreams);
            if (!SortingLayerExists(recipe.SortingLayer))
            {
                // 없는 이름을 넣으면 Unity 가 조용히 Default 로 그린다. 알리고 Default 로 둔다.
                result.Issue("build.bad_value", layer.Name, $"sortingLayer={recipe.SortingLayer} — 프로젝트에 없는 정렬 층, Default 로 둠");
            }
            else { renderer.sortingLayerName = recipe.SortingLayer; }
            renderer.sortingOrder = layer.SortOrder;
            if (material != null) { renderer.sharedMaterial = material; }
        }

        private static bool SortingLayerExists(string name)
        {
            foreach (SortingLayer sortingLayer in SortingLayer.layers)
            {
                if (sortingLayer.name == name) { return true; }
            }
            return false;
        }

        public static ParticleSystemSimulationSpace ParseSpace(string space, string layer, string field, VfxResult result)
        {
            if (space == null || space == "local") { return ParticleSystemSimulationSpace.Local; }
            if (space == "world") { return ParticleSystemSimulationSpace.World; }
            result.Issue("build.bad_value", layer, $"{field}={space} — local 로 둠");
            return ParticleSystemSimulationSpace.Local;
        }

        private static bool TryParseShape(string name, out ParticleSystemShapeType type)
        {
            switch (name)
            {
                case "Circle": type = ParticleSystemShapeType.Circle; return true;
                case "Cone": type = ParticleSystemShapeType.Cone; return true;
                case "Box": type = ParticleSystemShapeType.Box; return true;
                case "Edge": type = ParticleSystemShapeType.SingleSidedEdge; return true;
                case "Sphere": type = ParticleSystemShapeType.Sphere; return true;
                default: type = ParticleSystemShapeType.Circle; return false;
            }
        }

        // [x, y] 나 [x, y, z]. 빠진 z 는 fill 로 채운다(box 는 1, 위치 · 회전은 0).
        private static Vector3 ToVector3(float[] values, float fill)
        {
            var v = new Vector3(fill, fill, fill);
            if (values.Length > 0) { v.x = values[0]; }
            if (values.Length > 1) { v.y = values[1]; }
            if (values.Length > 2) { v.z = values[2]; }
            return v;
        }
    }
}
