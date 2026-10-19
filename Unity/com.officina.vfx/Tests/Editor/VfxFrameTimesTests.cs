using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 렌더 쪽 순수 셈 — 프레임 수 · 시각 · 정사영 크기 · 그림 크기 · 파일 이름.
    public class VfxFrameTimesTests
    {
        private static VfxRecipe Recipe(string json)
        {
            return VfxRecipe.Parse(json);
        }

        [Test]
        public void OneShotSkipsZeroAndCoversLifetime()
        {
            var recipe = Recipe("{\"name\":\"a\",\"duration\":0.5,\"fps\":12,\"layers\":[{\"name\":\"s\","
                + "\"main\":{\"startLifetime\":{\"random\":[0.25,0.45]},\"startDelay\":0.05}}]}");
            var frames = VfxFrameTimes.Compute(recipe);
            Assert.AreEqual(12, frames.Count); // ceil((0.5 + 0.05 + 0.45) × 12) = 12
            Assert.AreEqual(1, frames[0].I);
            Assert.AreEqual(0.5f / 12f, frames[0].T, 1e-5f);
            Assert.AreEqual(11.5f / 12f, frames[11].T, 1e-5f);
        }

        [Test]
        public void FirstFrameLandsInFlipbookCellZero()
        {
            // 플립북 0번 칸은 [0, 1/fps). 첫 장이 거기 들어가야 0번 칸이 찍힌다. 장 k 는 k번 칸 안.
            var recipe = Recipe("{\"name\":\"a\",\"duration\":0.5,\"fps\":12,\"layers\":[{\"name\":\"s\","
                + "\"main\":{\"startLifetime\":0.5}}]}");
            var frames = VfxFrameTimes.Compute(recipe);
            Assert.That(frames[0].T, Is.GreaterThanOrEqualTo(0f).And.LessThan(1f / 12f));
            for (int k = 0; k < frames.Count; k++)
            {
                Assert.That(frames[k].T, Is.GreaterThanOrEqualTo(k / 12f).And.LessThan((k + 1) / 12f));
            }
        }

        [Test]
        public void OneShotCapsAt48()
        {
            var recipe = Recipe("{\"name\":\"a\",\"duration\":3,\"fps\":24,\"layers\":[]}");
            Assert.AreEqual(VfxFrameTimes.MaxFrames, VfxFrameTimes.Compute(recipe).Count);
        }

        [Test]
        public void LoopStartsAfterOneCycle()
        {
            var recipe = Recipe("{\"name\":\"a\",\"duration\":1,\"fps\":12,\"loop\":true,\"layers\":[]}");
            var frames = VfxFrameTimes.Compute(recipe);
            Assert.AreEqual(12, frames.Count);
            Assert.AreEqual(1f + 0.5f / 12f, frames[0].T, 1e-5f);
            Assert.AreEqual(1f + 11.5f / 12f, frames[11].T, 1e-5f);
            Assert.Less(frames[11].T, 2f); // 꼬리 장도 한 바퀴 안
        }

        [Test]
        public void CameraAndPixelSize()
        {
            var recipe = Recipe("{\"name\":\"a\",\"ppu\":32,\"canvas\":{\"texels\":[48,64],\"scale\":4},\"layers\":[]}");
            Assert.AreEqual(1f, VfxFrameTimes.OrthoSize(recipe), 1e-6f);
            Assert.AreEqual(new Vector2Int(192, 256), VfxFrameTimes.PixelSize(recipe));
        }

        [Test]
        public void DefaultsWhenCanvasMissing()
        {
            var recipe = Recipe("{\"name\":\"a\",\"layers\":[]}");
            Assert.AreEqual(1f, VfxFrameTimes.OrthoSize(recipe), 1e-6f);
            Assert.AreEqual(new Vector2Int(256, 256), VfxFrameTimes.PixelSize(recipe));
        }

        [Test]
        public void FileNames()
        {
            Assert.AreEqual("f001.png", VfxFrameTimes.FileName(1, ""));
            Assert.AreEqual("f012_k.png", VfxFrameTimes.FileName(12, "_k"));
            Assert.AreEqual("f048_w.png", VfxFrameTimes.FileName(48, "_w"));
        }
    }
}
