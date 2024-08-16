import pulumi
import pulumi_gcp as gcp

class gcStorage:

    def __init__(self, bucketname, location):
        self.bucketname = bucketname
        self.location = location

    def makebucket(self):
        newbucket = gcp.storage.Bucket(self.bucketname,
            name=self.bucketname,
            location=self.location,
            lifecycle_rules=[gcp.storage.BucketLifecycleRuleArgs(
                action=gcp.storage.BucketLifecycleRuleActionArgs(
                    type="Delete",
                ),
                condition=gcp.storage.BucketLifecycleRuleConditionArgs(
                    days_since_noncurrent_time=3,
                    no_age=True,
                ),
            )])            

        return newbucket