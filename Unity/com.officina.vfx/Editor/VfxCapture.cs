using System;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using Object = UnityEngine.Object;

namespace Officina.Vfx.Editor
{
    // 카메라 한 장을 ARGB32 RT 에 그려 RGBA PNG 로 쓴다. SingleCameraRequest 가 안 되면 Camera.Render (실측 ②).
    // RT 와 읽기용 Texture2D 는 한 번 만들어 판 내내 다시 쓴다(프레임마다 만들고 지우면 배치 판이 길 때 느리고 샌다).
    public sealed class VfxCapture : IDisposable
    {
        public const string ApiRequest = "SingleCameraRequest";
        public const string ApiCameraRender = "Camera.Render";

        private readonly Vector2Int size;
        private RenderTexture rt;
        private Texture2D texture;

        public VfxCapture(Vector2Int size)
        {
            this.size = size;
            rt = new RenderTexture(size.x, size.y, 24, RenderTextureFormat.ARGB32);
            rt.Create();
            texture = new Texture2D(size.x, size.y, TextureFormat.RGBA32, false);
        }

        // 한 장만 찍을 때 쓰는 편의 함수. 돌려주는 값은 실제로 쓴 렌더 API 이름.
        public static string Grab(Camera camera, Vector2Int size, string pngPath)
        {
            using (var capture = new VfxCapture(size)) { return capture.Grab(camera, pngPath); }
        }

        public string Grab(Camera camera, string pngPath)
        {
            if (rt == null) { throw new ObjectDisposedException(nameof(VfxCapture)); }
            camera.targetTexture = rt;
            string api = ApiRequest;
            try
            {
                var request = new UniversalRenderPipeline.SingleCameraRequest { destination = rt };
                if (RenderPipeline.SupportsRenderRequest(camera, request)) { RenderPipeline.SubmitRenderRequest(camera, request); }
                else
                {
                    camera.Render();
                    api = ApiCameraRender;
                }
            }
            finally { camera.targetTexture = null; }

            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            try
            {
                texture.ReadPixels(new Rect(0, 0, size.x, size.y), 0, 0);
                texture.Apply();
            }
            finally { RenderTexture.active = previous; }

            File.WriteAllBytes(pngPath, texture.EncodeToPNG());
            return api;
        }

        public void Dispose()
        {
            if (texture != null) { Object.DestroyImmediate(texture); texture = null; }
            if (rt != null)
            {
                rt.Release();
                Object.DestroyImmediate(rt);
                rt = null;
            }
        }
    }
}
