using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using NUnit.Framework;
using Officina.Vfx.Editor;

namespace Officina.Vfx.Tests
{
    // 묶어 굽기 목록(jobs.json) 읽기와 -vfxJob · -vfxJobs 가르기를 본다 (묶어굽기설계 2-1 · 2-2).
    public class VfxJobListTests
    {
        private string dir;

        [SetUp]
        public void SetUp()
        {
            dir = Path.Combine(Path.GetTempPath(), "VfxJobListTests_" + Path.GetRandomFileName());
            Directory.CreateDirectory(dir);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(dir)) { Directory.Delete(dir, true); }
        }

        private string JobPath(int index)
        {
            return Path.Combine(dir, "v" + index, "job.json");
        }

        private string WriteList(string json)
        {
            string path = Path.Combine(dir, "jobs.json");
            File.WriteAllText(path, json);
            return path;
        }

        private string WriteJobs(IEnumerable<string> jobs)
        {
            return WriteList(JsonConvert.SerializeObject(new Dictionary<string, object> { ["jobs"] = jobs }));
        }

        [Test]
        public void LoadsAbsolutePathsInOrder()
        {
            VfxJobList list = VfxJobList.Load(WriteJobs(new[] { JobPath(0), JobPath(1) }));
            CollectionAssert.AreEqual(new[] { JobPath(0), JobPath(1) }, list.Jobs);
        }

        [Test]
        public void RejectsUnknownField()
        {
            string json = "{ \"jobs\": [" + JsonConvert.ToString(JobPath(0)) + "], \"job\": 1 }";
            Assert.Throws<JsonSerializationException>(() => VfxJobList.Load(WriteList(json)));
        }

        [Test]
        public void RejectsEmptyOrMissingList()
        {
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteList("{ \"jobs\": [] }")));
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteList("{ }")));
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteList("")));
        }

        [Test]
        public void RejectsRelativeOrBlankPath()
        {
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(0), "v1/job.json" })));
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(0), "" })));
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(0), null })));
        }

        [Test]
        public void RejectsSamePathTwice()
        {
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(0), JobPath(1), JobPath(0) })));
            // 대소문자 · 구분자만 다른 같은 자리도 같은 result.json 을 덮으므로 겹침이다.
            string twin = JobPath(1).ToUpperInvariant().Replace('\\', '/');
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(1), twin })));
        }

        [Test]
        public void RejectsTwoJobsInOneFolder()
        {
            // 판 결과는 job.json 옆 result.json 이라 폴더가 같으면 서로 덮는다.
            string other = Path.Combine(Path.GetDirectoryName(JobPath(0)), "job2.json");
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(new[] { JobPath(0), other })));
        }

        [Test]
        public void AcceptsUpToMaxJobs()
        {
            var jobs = new List<string>();
            for (int i = 0; i < VfxJobList.MaxJobs; i++) { jobs.Add(JobPath(i)); }
            Assert.AreEqual(48, VfxJobList.MaxJobs);
            Assert.AreEqual(48, VfxJobList.Load(WriteJobs(jobs)).Jobs.Count);
            jobs.Add(JobPath(VfxJobList.MaxJobs));
            Assert.Throws<VfxBuildException>(() => VfxJobList.Load(WriteJobs(jobs)));
        }

        [Test]
        public void ListArgPicksMode()
        {
            Assert.AreEqual("D:/w/jobs.json", VfxEntry.ListArg(new[] { "Unity.exe", "-batchmode", "-vfxJobs", "D:/w/jobs.json" }));
            Assert.IsNull(VfxEntry.ListArg(new[] { "Unity.exe", "-vfxJob", "D:/w/job.json" }));
            // 둘 다 없으면 단일 경로로 넘겨 지금과 같은 「-vfxJob 이 없다」 종료 2 를 낸다.
            Assert.IsNull(VfxEntry.ListArg(new[] { "Unity.exe", "-batchmode" }));
            Assert.Throws<VfxBuildException>(() => VfxEntry.ListArg(new[] { "-vfxJob", "a/job.json", "-vfxJobs", "b/jobs.json" }));
        }
    }
}
